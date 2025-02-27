# Copyright 2021-2024 Avaiga Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import itertools
from datetime import datetime
from multiprocessing import Lock
from queue import Queue
from time import sleep
from typing import Callable, Dict, Iterable, List, Optional, Set, Union

from taipy.config.config import Config
from taipy.logger._taipy_logger import _TaipyLogger

from .._entity.submittable import Submittable
from ..data._data_manager_factory import _DataManagerFactory
from ..job._job_manager_factory import _JobManagerFactory
from ..job.job import Job
from ..job.job_id import JobId
from ..submission._submission_manager_factory import _SubmissionManagerFactory
from ..submission.submission import Submission
from ..task.task import Task
from ._abstract_orchestrator import _AbstractOrchestrator


class _Orchestrator(_AbstractOrchestrator):
    """
    Handles the functional orchestrating.
    """

    jobs_to_run: Queue = Queue()
    blocked_jobs: List = []
    lock = Lock()
    __logger = _TaipyLogger._get_logger()
    _submission_entities: Dict[str, Submission] = {}

    @classmethod
    def initialize(cls):
        pass

    @classmethod
    def submit(
        cls,
        submittable: Submittable,
        callbacks: Optional[Iterable[Callable]] = None,
        force: bool = False,
        wait: bool = False,
        timeout: Optional[Union[float, int]] = None,
        **properties,
    ) -> Submission:
        """Submit the given `Scenario^` or `Sequence^` for an execution.

        Parameters:
             submittable (Union[SCenario^, Sequence^]): The scenario or sequence to submit for execution.
             callbacks: The optional list of functions that should be executed on jobs status change.
             force (bool) : Enforce execution of the scenario's or sequence's tasks even if their output data
                nodes are cached.
             wait (bool): Wait for the orchestrated jobs created from the scenario or sequence submission to be
                finished in asynchronous mode.
             timeout (Union[float, int]): The optional maximum number of seconds to wait for the jobs to be finished
                before returning.
             **properties (dict[str, any]): A keyworded variable length list of additional arguments.
        Returns:
            The created Jobs.
        """
        submission = _SubmissionManagerFactory._build_manager()._create(
            submittable.id,  # type: ignore
            submittable._ID_PREFIX,  # type: ignore
            getattr(submittable, "config_id", None),
            **properties,
        )
        cls._submission_entities[submission.id] = submission
        jobs = []
        tasks = submittable._get_sorted_tasks()
        with cls.lock:
            for ts in tasks:
                for task in ts:
                    jobs.append(
                        cls._lock_dn_output_and_create_job(
                            task,
                            submission.id,
                            submission.entity_id,
                            callbacks=itertools.chain([cls._update_submission_status], callbacks or []),
                            force=force,  # type: ignore
                        )
                    )
        submission.jobs = jobs  # type: ignore
        cls._orchestrate_job_to_run_or_block(jobs)
        if Config.job_config.is_development:
            cls._check_and_execute_jobs_if_development_mode()
        else:
            if wait:
                cls._wait_until_job_finished(jobs, timeout=timeout)
        return submission

    @classmethod
    def submit_task(
        cls,
        task: Task,
        callbacks: Optional[Iterable[Callable]] = None,
        force: bool = False,
        wait: bool = False,
        timeout: Optional[Union[float, int]] = None,
        **properties,
    ) -> Submission:
        """Submit the given `Task^` for an execution.

        Parameters:
             task (Task^): The task to submit for execution.
             callbacks: The optional list of functions that should be executed on job status change.
             force (bool): Enforce execution of the task even if its output data nodes are cached.
             wait (bool): Wait for the orchestrated job created from the task submission to be finished
                in asynchronous mode.
             timeout (Union[float, int]): The optional maximum number of seconds to wait for the job
                to be finished before returning.
             **properties (dict[str, any]): A keyworded variable length list of additional arguments.
        Returns:
            The created `Job^`.
        """
        submission = _SubmissionManagerFactory._build_manager()._create(
            task.id, task._ID_PREFIX, task.config_id, **properties
        )
        submit_id = submission.id
        cls._submission_entities[submission.id] = submission
        with cls.lock:
            job = cls._lock_dn_output_and_create_job(
                task,
                submit_id,
                submission.entity_id,
                itertools.chain([cls._update_submission_status], callbacks or []),
                force,
            )
        jobs = [job]
        submission.jobs = jobs  # type: ignore
        cls._orchestrate_job_to_run_or_block(jobs)
        if Config.job_config.is_development:
            cls._check_and_execute_jobs_if_development_mode()
        else:
            if wait:
                cls._wait_until_job_finished(job, timeout=timeout)
        return submission

    @classmethod
    def _update_submission_status(cls, job: Job):
        cls._submission_entities[job.submit_id]._update_submission_status(job)

    @classmethod
    def _lock_dn_output_and_create_job(
        cls,
        task: Task,
        submit_id: str,
        submit_entity_id: str,
        callbacks: Optional[Iterable[Callable]] = None,
        force: bool = False,
    ) -> Job:
        for dn in task.output.values():
            dn.lock_edit()
        job = _JobManagerFactory._build_manager()._create(
            task, itertools.chain([cls._on_status_change], callbacks or []), submit_id, submit_entity_id, force=force
        )

        return job

    @classmethod
    def _orchestrate_job_to_run_or_block(cls, jobs: List[Job]):
        blocked_jobs = []
        pending_jobs = []

        for job in jobs:
            if cls._is_blocked(job):
                job.blocked()
                blocked_jobs.append(job)
            else:
                job.pending()
                pending_jobs.append(job)

        cls.blocked_jobs.extend(blocked_jobs)
        for job in pending_jobs:
            cls.jobs_to_run.put(job)

    @classmethod
    def _wait_until_job_finished(cls, jobs: Union[List[Job], Job], timeout: Optional[Union[float, int]] = None):
        #  Note: this method should be prefixed by two underscores, but it has only one, so it can be mocked in tests.
        def __check_if_timeout(st, to):
            if to:
                return (datetime.now() - st).seconds < to
            return True

        start = datetime.now()
        jobs = jobs if isinstance(jobs, Iterable) else [jobs]
        index = 0
        while __check_if_timeout(start, timeout) and index < len(jobs):
            try:
                if jobs[index]._is_finished():
                    index = index + 1
                else:
                    sleep(0.5)  # Limit CPU usage
            except Exception:
                pass

    @classmethod
    def _is_blocked(cls, obj: Union[Task, Job]) -> bool:
        """Returns True if the execution of the `Job^` or the `Task^` is blocked by the execution of another `Job^`.

        Parameters:
             obj (Union[Task^, Job^]): The job or task entity to run.

        Returns:
             True if one of its input data nodes is blocked.
        """
        input_data_nodes = obj.task.input.values() if isinstance(obj, Job) else obj.input.values()
        data_manager = _DataManagerFactory._build_manager()
        return any(not data_manager._get(dn.id).is_ready_for_reading for dn in input_data_nodes)

    @staticmethod
    def _unlock_edit_on_jobs_outputs(jobs: Union[Job, List[Job], Set[Job]]):
        jobs = [jobs] if isinstance(jobs, Job) else jobs
        for job in jobs:
            job._unlock_edit_on_outputs()

    @classmethod
    def _on_status_change(cls, job: Job):
        if job.is_completed() or job.is_skipped():
            cls.__unblock_jobs()
        elif job.is_failed():
            cls._fail_subsequent_jobs(job)

    @classmethod
    def __unblock_jobs(cls):
        for job in cls.blocked_jobs:
            if not cls._is_blocked(job):
                with cls.lock:
                    job.pending()
                    cls.__remove_blocked_job(job)
                    cls.jobs_to_run.put(job)

    @classmethod
    def __remove_blocked_job(cls, job):
        try:  # In case the job has been removed from the list of blocked_jobs.
            cls.blocked_jobs.remove(job)
        except Exception:
            cls.__logger.warning(f"{job.id} is not in the blocked list anymore.")

    @classmethod
    def cancel_job(cls, job: Job):
        if job.is_canceled():
            cls.__logger.info(f"{job.id} has already been canceled.")
        elif job.is_abandoned():
            cls.__logger.info(f"{job.id} has already been abandoned and cannot be canceled.")
        elif job.is_failed():
            cls.__logger.info(f"{job.id} has already failed and cannot be canceled.")
        else:
            with cls.lock:
                to_cancel_or_abandon_jobs = set([job])
                to_cancel_or_abandon_jobs.update(cls.__find_subsequent_jobs(job.submit_id, set(job.task.output.keys())))
                cls.__remove_blocked_jobs(to_cancel_or_abandon_jobs)
                cls.__remove_jobs_to_run(to_cancel_or_abandon_jobs)
                cls._cancel_jobs(job.id, to_cancel_or_abandon_jobs)
                cls._unlock_edit_on_jobs_outputs(to_cancel_or_abandon_jobs)

    @classmethod
    def __find_subsequent_jobs(cls, submit_id, output_dn_config_ids: Set) -> Set[Job]:
        next_output_dn_config_ids = set()
        subsequent_jobs = set()
        for job in cls.blocked_jobs:
            job_input_dn_config_ids = job.task.input.keys()
            if job.submit_id == submit_id and len(output_dn_config_ids.intersection(job_input_dn_config_ids)) > 0:
                next_output_dn_config_ids.update(job.task.output.keys())
                subsequent_jobs.update([job])
        if len(next_output_dn_config_ids) > 0:
            subsequent_jobs.update(
                cls.__find_subsequent_jobs(submit_id, output_dn_config_ids=next_output_dn_config_ids)
            )
        return subsequent_jobs

    @classmethod
    def __remove_blocked_jobs(cls, jobs):
        for job in jobs:
            cls.__remove_blocked_job(job)

    @classmethod
    def __remove_jobs_to_run(cls, jobs):
        new_jobs_to_run: Queue = Queue()
        while not cls.jobs_to_run.empty():
            current_job = cls.jobs_to_run.get()
            if current_job not in jobs:
                new_jobs_to_run.put(current_job)
        cls.jobs_to_run = new_jobs_to_run

    @classmethod
    def _fail_subsequent_jobs(cls, failed_job: Job):
        with cls.lock:
            to_fail_or_abandon_jobs = set()
            to_fail_or_abandon_jobs.update(
                cls.__find_subsequent_jobs(failed_job.submit_id, set(failed_job.task.output.keys()))
            )
            for job in to_fail_or_abandon_jobs:
                job.abandoned()
            to_fail_or_abandon_jobs.update([failed_job])
            cls.__remove_blocked_jobs(to_fail_or_abandon_jobs)
            cls.__remove_jobs_to_run(to_fail_or_abandon_jobs)
            cls._unlock_edit_on_jobs_outputs(to_fail_or_abandon_jobs)

    @classmethod
    def _cancel_jobs(cls, job_id_to_cancel: JobId, jobs: Set[Job]):
        from ._orchestrator_factory import _OrchestratorFactory

        for job in jobs:
            if job.id in _OrchestratorFactory._dispatcher._dispatched_processes.keys():  # type: ignore
                cls.__logger.info(f"{job.id} is running and cannot be canceled.")
            elif job.is_completed():
                cls.__logger.info(f"{job.id} has already been completed and cannot be canceled.")
            elif job.is_skipped():
                cls.__logger.info(f"{job.id} has already been skipped and cannot be canceled.")
            else:
                if job_id_to_cancel == job.id:
                    job.canceled()
                else:
                    job.abandoned()

    @staticmethod
    def _check_and_execute_jobs_if_development_mode():
        from ._orchestrator_factory import _OrchestratorFactory

        if dispatcher := _OrchestratorFactory._dispatcher:
            dispatcher._execute_jobs_synchronously()
