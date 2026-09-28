from typing import Generic, TypeVar, Type, Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    """Base repository for generic CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize repository with model class and database session."""
        self.model = model
        self.session = session

    async def get_by_id(self, id: str) -> Optional[ModelType]:
        """Get a record by its UUID."""
        result = await self.session.execute(select(self.model).filter(self.model.id == id))
        return result.scalars().first()

    async def get_all(self) -> List[ModelType]:
        """Get all records of this model."""
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    async def create(self, obj_in: Dict[str, Any]) -> ModelType:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(self, db_obj: ModelType, obj_in: Dict[str, Any]) -> ModelType:
        """Update a record."""
        for key, value in obj_in.items():
            setattr(db_obj, key, value)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, db_obj: ModelType) -> None:
        """Delete a record."""
        await self.session.delete(db_obj)
        await self.session.commit()
