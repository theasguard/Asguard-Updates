"""
    Asguard Addon
    Copyright (C) 2016 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import queue
import threading
import log_utils

logger = log_utils.Logger.get_logger(__name__)

Empty = queue.Empty

class WorkerPool:
    def __init__(self, max_workers=None):
        self.max_workers = max_workers
        self.workers = []
        self.out_q = queue.Queue()
        self.in_q = queue.Queue()
        self.new_job = threading.Event()
        self.manager = None
        self.closing = False
        self.__start_manager()
    
    def request(self, func, args=None, kwargs=None):
        args = args if args is not None else []
        kwargs = kwargs if kwargs is not None else {}
        self.in_q.put({'func': func, 'args': args, 'kwargs': kwargs})
        self.new_job.set()
    
    def receive(self, timeout=None):
        try:
            return self.out_q.get(True, timeout)
        except queue.Empty:
            logger.log('Timeout occurred while waiting for job result.', log_utils.LOGWARNING)
            return None
    
    def close(self):
        self.closing = True
        self.new_job.set()

        # Signal all consumers to terminate
        self.in_q.put(None)
        if self.manager is not None:
            self.manager.join()
            
        return reap_workers(self.workers)

    def __start_manager(self):
        self.manager = threading.Thread(target=self.__manage_consumers)
        self.manager.daemon = True
        self.manager.start()
        logger.log(f'Pool Manager({self}): started.', log_utils.LOGDEBUG)
        
    def __manage_consumers(self):
        while not self.closing:
            self.new_job.wait()
            self.new_job.clear()
            if self.closing:
                break
            
            new_workers = self.in_q.qsize()  # Create a worker for each job waiting (up to max_workers)
            if new_workers > 0:
                max_new = new_workers if self.max_workers is None else self.max_workers - len(self.workers)
                    
                if max_new > 0:
                    logger.log(f'Pool Manager: Requested: {new_workers} Allowed: {max_new} - Pool Size: ({len(self.workers)} / {self.max_workers})', log_utils.LOGDEBUG)
                    new_workers = min(new_workers, max_new)
                        
                    for _ in range(new_workers):
                        try:
                            worker = threading.Thread(target=self.consumer)
                            worker.daemon = True
                            worker.start()
                            self.workers.append(worker)
                            logger.log(f'Pool Manager: {worker.name} thrown in Pool: ({len(self.workers)}/{self.max_workers})', log_utils.LOGDEBUG)
                        except RuntimeError as e:
                            try: logger.log('Pool Manager: %s missed Pool: %s - (%s/%s)' % (worker.name, e, len(self.workers), self.max_workers), log_utils.LOGWARNING)
                            except UnboundLocalError: pass  # worker may not have gotten assigned
                        
        logger.log(f'Pool Manager({self}): quitting.', log_utils.LOGDEBUG)
            
    def consumer(self):
        me = threading.current_thread()
        while True:
            job = self.in_q.get()
            if job is None:
                logger.log(f'Worker: {me.name} committing suicide.', log_utils.LOGDEBUG)
                self.in_q.put(job)
                break
            
            # logger.log('Worker: %s handling job: |%s| with args: |%s| and kwargs: |%s|' % (me.name, job['func'], job['args'], job['kwargs']), log_utils.LOGDEBUG)
            result = job['func'](*job['args'], **job['kwargs'])
            self.out_q.put(result)
    
def reap_workers(workers, timeout=0):
    """
    Reap thread/process workers; don't block by default; return un-reaped workers
    """
    logger.log(f'In Reap: Total Workers: {len(workers)}', log_utils.LOGDEBUG)
    living_workers = []
    for worker in workers:
        if worker:
            logger.log(f'Reaping: {worker.name}', log_utils.LOGDEBUG)
            worker.join(timeout)
            if worker.is_alive():
                logger.log(f'Worker {worker.name} still running', log_utils.LOGDEBUG)
                living_workers.append(worker)
    return living_workers

