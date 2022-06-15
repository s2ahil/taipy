# Copyright 2022 Avaiga Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

from typing import Generic, Iterable, List, TypeVar, Union

from taipy.core._repository import _FileSystemRepository
from taipy.core.common._entity_ids import _EntityIds
from taipy.core.common._taipy_logger import _TaipyLogger
from taipy.core.exceptions.exceptions import ModelNotFound

EntityType = TypeVar("EntityType")


class _Manager(Generic[EntityType]):
    _repository: _FileSystemRepository
    _logger = _TaipyLogger._get_logger()
    _ENTITY_NAME: str = "Entity"

    @classmethod
    def _delete_all(cls):
        """
        Deletes all entities.
        """
        cls._repository._delete_all()

    @classmethod
    def _delete_many(cls, ids: Iterable):
        """
        Deletes entities by a list of ids.
        """
        cls._repository._delete_many(ids)

    @classmethod
    def _delete(cls, id):
        """
        Deletes an entity by id.
        """
        cls._repository._delete(id)

    @classmethod
    def _set(cls, entity: EntityType):
        """
        Save or update an entity.
        """
        cls._repository._save(entity)

    @classmethod
    def _get_all(cls) -> List[EntityType]:
        """
        Returns all entities.
        """
        return cls._repository._load_all()

    @classmethod
    def _get_all_by(cls, by) -> List[EntityType]:
        """
        Returns all entities.
        """
        return cls._repository._load_all_by(by)

    @classmethod
    def _get(cls, entity: Union[str, EntityType], default=None) -> EntityType:
        """
        Returns an entity by id or reference.
        """
        entity_id = entity if isinstance(entity, str) else entity.id  # type: ignore
        try:
            return cls._repository.load(entity_id)
        except ModelNotFound:
            cls._logger.error(f"{cls._ENTITY_NAME} not found: {entity_id}")
            return default

    @classmethod
    def _delete_entities_of_multiple_types(cls, _entity_ids: _EntityIds):
        """
        Deletes entities of multiple types.
        """
        from taipy.core.cycle._cycle_manager_factory import _CycleManagerFactory
        from taipy.core.data._data_manager_factory import _DataManagerFactory
        from taipy.core.job._job_manager_factory import _JobManagerFactory
        from taipy.core.pipeline._pipeline_manager_factory import _PipelineManagerFactory
        from taipy.core.scenario._scenario_manager_factory import _ScenarioManagerFactory
        from taipy.core.task._task_manager_factory import _TaskManagerFactory

        _CycleManagerFactory._build_manager()._delete_many(_entity_ids.cycle_ids)
        _ScenarioManagerFactory._build_manager()._delete_many(_entity_ids.scenario_ids)
        _PipelineManagerFactory._build_manager()._delete_many(_entity_ids.pipeline_ids)
        _TaskManagerFactory._build_manager()._delete_many(_entity_ids.task_ids)
        _JobManagerFactory._build_manager()._delete_many(_entity_ids.job_ids)
        _DataManagerFactory._build_manager()._delete_many(_entity_ids.data_node_ids)
