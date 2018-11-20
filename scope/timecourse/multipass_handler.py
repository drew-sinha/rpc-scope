import collections
import pathlib
from scope.timecourse import timecourse_handler

class MultiPassHandler(timecourse_handler.BasicAcquisitionHandler):
    '''
        This Handler performs two passes of the same image (and post-) acquisition sequence.
    '''
    REFOCUS_INTERVAL_MINS = 3*60 # re-run autofocus at least this often. Useful for not autofocusing every timepoint.
    DO_COARSE_FOCUS = False
    # 1 mm distance in 50 steps = 20 microns/step. So we should be somewhere within 20-40 microns of the right plane after coarse autofocus.
    COARSE_FOCUS_RANGE = 1
    COARSE_FOCUS_STEPS = 50

    FINE_FOCUS_RANGE = 0.05
    FINE_FOCUS_STEPS = 25
    PIXEL_READOUT_RATE = '100 MHz'
    USE_LAST_FOCUS_POSITION = True # if False, start autofocus from original z position rather than last autofocused position.
    INTERVAL_MODE = 'scheduled start'
    IMAGE_COMPRESSION = timecourse_handler.PNG_FAST
    LOG_LEVEL = timecourse_handler.logging.INFO

    FLUORESCENCE_FLATFIELD_LAMP_AF = 'green_yellow'
    DEVELOPMENT_TIME_HOURS = 45

    REVISIT_INTERVAL_MINS = 3
    NUM_TOTAL_VISITS = 7

    def configure_additional_acquisition_steps(self):
        """Add more steps to the acquisition_sequencer's sequence as desired,
        making sure to also add corresponding names to the image_name attribute.
        For example, to add a 200 ms GFP acquisition, a subclass may override
        this as follows:
            def configure_additional_acquisition_steps(self):
                self.scope.camera.acquisition_sequencer.add_step(exposure_ms=200,
                    lamp='cyan')
                self.image_names.append('gfp.png')
        """
        if time.time() - self.experiment_metadata['timestamps'][0] > self.DEVELOPMENT_TIME_HOURS*3600:
            self.scope.camera.acquisition_sequencer.add_step(exposure=50,lamp=self.FLUORESCENCE_FLATFIELD_LAMP_AF)
            self.image_names.append('autofluorescence.png')

    def iterate_on_positions(self):
        revisit_queue = collections.deque()
        for position_name, position_coords in sorted(self.positions.items()):
            while revisit_queue:
                next_revisit_time = revisit_queue[0][2] # Do a peek before popping
                if time.time() - revisit_time < 0: # Negative times are before the desired passback
                    break
                queued_position, queued_position_coords, revisit_time, visits_done = revisit_queue.popleft()
                new_metadata = self.run_position(queued_position, queued_position_coords, visits_done+1)
                visits_done += 1
                if visits_done < self.NUM_TOTAL_VISITS:
                    revisit_queue.append(
                        [queued_position,
                            position_coords,
                            new_metadata['image_timestamps'][self.image_names[-1]] + self.REVISIT_INTERVAL_MINS*60,
                            visits_done])
                self.heartbeat()

            if position_name not in self.skip_positions:
                new_metadata = self.run_position(position_name, position_coords, 1)
                if time.time() - self.experiment_metadata['timestamps'][0] > self.DEVELOPMENT_TIME_HOURS*3600
                    revisit_queue.append(
                        [position_name,
                            position_coords[:2] + new_metadata['fine_z'],
                            new_metadata['image_timestamps'][self.image_names[-1]] + self.REVISIT_INTERVAL_MINS*60,
                            1])
                self.heartbeat()

        # Finish out queue
        while revisit_queue:
            queued_position, queued_position_coords, revisit_time, visits_done = revisit_queue.popleft()
            if time.time() - revisit_time < 0: # Negative times are before the desired passback
                while (revisit_time - time.time()) < 60: # Handle heartbeat for excessively long delays
                    time.sleep(55)
                    self.heartbeat()

                time.sleep(revisit_time-time.time())
                self.heartbeat()

            new_metadata = self.run_position(queued_position, queued_position_coords, visits_done+1)
            visits_done += 1
            if visits_done < self.NUM_TOTAL_VISITS:
                revisit_queue.append(
                    [queued_position,
                        position_coords,
                        new_metadata['image_timestamps'][self.image_names[-1]] + self.REVISIT_INTERVAL_MINS*60,
                        visits_done])
            self.heartbeat()

    def run_position(self, position_name, position_coords, visit_num):
        """Do everything required for taking a timepoint at a single position
        EXCEPT focusing / image acquisition. This includes moving the stage to
        the right x,y position, loading and saving metadata, and saving image
        data, as generated by acquire_images()"""

        if visit_num == 1:
            self.logger.info(f'Acquiring Position: {position_name}')
        else:
            self.logger.info('Acquiring Position: {position_name} - visit {visit_num}')

        t0 = time.time()
        timestamp = time.time()
        position_dir, metadata_path, position_metadata = self._position_metadata(position_name)
        position_dir.mkdir(exist_ok=True)
        if self.scope is not None:
            self.scope.stage.position = position_coords
        t1 = time.time()
        self.logger.debug('Stage Positioned ({:.1f} seconds)', t1-t0)
        images, image_names, new_metadata = self.acquire_images(position_name, position_dir,    # new_metadata should always be what goes into most current entry of metadata regardless of which pass
            position_metadata, visit_num)
        t2 = time.time()
        self.logger.debug('{} Images Acquired ({:.1f} seconds)', len(images), t2-t1)

        image_paths = [position_dir / (self.timepoint_prefix + ' ' + name) for name in image_names]
        if new_metadata is None:
            new_metadata = {}

        if visit_num == 1:
            new_metadata['timepoint'] = self.timepoint_prefix
            new_metadata['timestamp'] = timestamp

        if self.write_files:
            futures_out = self.image_io.write(images, image_paths, self.IMAGE_COMPRESSION, wait=False)
            self._job_futures.extend(futures_out)

            if visit_num == self.NUM_TOTAL_VISITS:
                position_metadata.append(new_metadata)
                self._write_atomic_json(metadata_path, position_metadata)
        t3 = time.time()
        self.logger.debug('Images saved ({:.1f} seconds)', t3-t2)
        self.logger.debug('Position done (total: {:.1f} seconds)', t3-t0)

        return new_metadata

    def acquire_images(self, position_name, position_dir, position_metadata, visit_num):
        t0 = time.time()
        self.scope.camera.exposure_time = self.bf_exposure
        self.scope.tl.lamp.intensity = self.tl_intensity
        metadata = {}
        last_autofocus_time = 0
        if self.USE_LAST_FOCUS_POSITION:
            last_z = self.positions[position_name][2]
            for m in position_metadata[::-1]:
                if 'fine_z' in m:
                    last_autofocus_time = m['timestamp']
                    last_z = m['fine_z']
                    break
            self.scope.stage.z = last_z

        override_autofocus = False
        z_updates = self.experiment_metadata.get('z_updates', {})
        if len(z_updates) > 0:
            latest_update_isotime = sorted(z_updates.keys())[-1]
            last_autofocus_isotime = datetime.datetime.fromtimestamp(last_autofocus_time).isoformat()
            if latest_update_isotime > last_autofocus_isotime:
                latest_z_update = z_updates[latest_update_isotime]
                if position_name in latest_z_update:
                    z = latest_z_update[position_name]
                    self.logger.info('Using updated z: {}', z)
                    self.scope.stage.z = z
                    metadata['fine_z'] = z
                    override_autofocus = True

        save_focus_stack = False
        due_for_autofocus = t0 - last_autofocus_time > self.REFOCUS_INTERVAL_MINS * 60
        if (not override_autofocus and due_for_autofocus): # Don't worry about autofocusing in the middle of a run. Handled with the queue
            if position_name in self.experiment_metadata.get('save_focus_stacks', []):
                save_focus_stack = True
            best_z, focus_scores, focus_images = self.run_autofocus(position_name, metadata, save_focus_stack)
            t1 = time.time()
            self.logger.debug('Autofocused ({:.1f} seconds)', t1-t0)
            self.logger.info('Autofocus z: {}', metadata['fine_z'])
        else:
            t1 = time.time()

        images = self.scope.camera.acquisition_sequencer.run()
        t2 = time.time()
        self.logger.debug('Acquisition sequence run ({:.1f} seconds)', t2-t1)
        exposures = self.scope.camera.acquisition_sequencer.exposure_times
        timestamps = list(self.scope.camera.acquisition_sequencer.latest_timestamps)
        self.post_acquisition_sequence(position_name, position_dir, position_metadata, metadata, images, exposures, timestamps)
        images = [self.dark_corrector.correct(image, exposure) for image, exposure in zip(images, exposures)]
        if None in timestamps:
            self.logger.warning('None value found in timestamp! Timestamps = {}', timestamps)
            timestamps = [t if t is not None else numpy.nan for t in timestamps]
        timestamps = (numpy.array(timestamps) - timestamps[0]) / self.scope.camera.timestamp_hz

        image_names = [image_name + f'_{visit_num}' for image_name in self.image_names]
        image_timestamps = metadata.get('image_timestamps', {})
        image_timestamps.update(zip(self.image_names, timestamps))
        metadata['image_timestamps'] = image_timestamps

        if visit_num == 1 and save_focus_stack and self.write_files:
            save_image_dir = position_dir / f'{self.timepoint_prefix} focus'
            save_image_dir.mkdir(exist_ok=True)
            pad = int(numpy.ceil(numpy.log10(self.FINE_FOCUS_STEPS - 1)))
            image_paths = [save_image_dir / f'{i:0{pad}}.png' for i in range(self.FINE_FOCUS_STEPS)]
            z, scores = zip(*focus_scores)
            focus_data = dict(z=z, scores=scores, best_index=numpy.argmax(scores))
            self._write_atomic_json(save_image_dir / 'focus_data.json', focus_data)
            with self.heartbeat_timer():
                self.image_io.write(focus_images, image_paths, self.IMAGE_COMPRESSION)

        return images, image_names, metadata

    def post_acquisition_sequence(self, position_name, position_dir, position_metadata, current_timepoint_metadata, images, exposures, timestamps):
        """Run any necessary image acquisitions, etc, after the main acquisition
        sequence finishes. (E.g. for light stimulus and post-stimulus recording.)

        Parameters:
            position_name: name of the position in the experiment metadata file.
            position_dir: pathlib.Path object representing the directory where
                position-specific data files and outputs are written. Useful for
                reading previous image data.
            position_metadata: list of all the stored position metadata from the
                previous timepoints, in chronological order.
            current_timepoint_metadata: the metatdata for the current timepoint.
                It may be used to append to keys like 'image_timestamps' etc.
            images: list of acquired images. Newly-acquired images should be
                appended to this list.
            exposures: list of exposure times for acquired images. If additional
                images are acquired, their exposure times should be appended.
            timestamps: list of camera timestamps for acquired images. If
                additional images are acquired, their timestamps should be appended.
        """
        # remember to call self.heartbeat() at least once every minute or so
        pass

    def get_next_run_interval(self, experiment_hours):
        """Return the delay interval, in hours, before the experiment should be
        run again.

        The interval will be interpreted according to the INTERVAL_MODE attribute,
        as described in the class documentation. Returning None indicates that
        timepoints should not be acquired again.

        Parameters:
            experiment_hours: number of hours between the start of the first
                timepoint and the start of this timepoint.
        """
        return $run_interval

if __name__ == '__main__':
    # note: can add any desired keyword arguments to the Handler init method
    # to the below call to main(), which is defined by scope.timecourse.base_handler.TimepointHandler
    Handler.main(pathlib.Path(__file__).parent)
