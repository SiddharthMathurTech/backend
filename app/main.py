from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List,AsyncGenerator 
import uuid
from sqlalchemy import Column, String, Boolean, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, case
import re




# ----- Database things ---
# Railway PostgreSQL credentials
POSTGRES_DATABASE_NAME: str = "railway"  # Changed from "hrms" to "railway"
POSTGRES_DATABASE_HOST: str = "turntable.proxy.rlwy.net"  # Changed from "localhost"
POSTGRES_DATABASE_PORT: str = "51332"  # Changed from "5432"
POSTGRES_DATABASE_USER: str = "postgres"  # Same username
POSTGRES_DATABASE_PASSWORD: str = "otmUYTINQWUFWVmcZTNsURFptWGmkhKm"  # Changed from "123456"


POSTGRES_DATABASE_URL: str = (
    f"postgresql+asyncpg://{POSTGRES_DATABASE_USER}:{POSTGRES_DATABASE_PASSWORD}@{POSTGRES_DATABASE_HOST}:{POSTGRES_DATABASE_PORT}/{POSTGRES_DATABASE_NAME}"
)

# Create an async database engine
postgres_engine: AsyncEngine = create_async_engine(
    POSTGRES_DATABASE_URL,
    echo=True,
    future=True
)

# Create async sessionmaker
SessionLocal = sessionmaker(
    bind=postgres_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Declare base for models
SQLAlchemyBase = declarative_base()

# ----- SQLAlchemy Model -----
class User(SQLAlchemyBase):
    __tablename__ = "user"
    __table_args__ = {"extend_existing": True}
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    firstname = Column(String, nullable=True)
    lastname = Column(String, nullable=True)
    isactive = Column(Boolean, nullable=False, server_default=text("true"))
    emailaddress = Column(String, nullable=False)
    department = Column(String, nullable=False)
    user_company_id = Column(String, nullable=False)


from sqlalchemy import Date, ForeignKey, DateTime
from datetime import datetime
class Attendance(SQLAlchemyBase):
    __tablename__ = "attendance"

    attendance_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))

    user_id = Column(UUID(as_uuid=True), nullable=False)

    attendance_date = Column(Date, nullable=False)

    status = Column(String(10), nullable=False)  # Present / Absent

    created_at = Column(DateTime, default=datetime.utcnow)


# ----- Pydantic Schemas -----
class AddEmployeeSchemaRequest(BaseModel):
    firstName: Optional[str] = Field(None, description="Employee's first name")
    lastName: Optional[str] = Field(None, description="Employee's last name")
    emailAddress: EmailStr = Field(..., description="Employee's email address")
    department: str = Field(..., description="Employee's department")

    

    class Config:
        json_schema_extra = {
            "example": {
                "firstName": "John",
                "lastName": "Doe",
                "emailaddress": "john.doe@company.com",
                "department": "Engineering",
            }
        }

from datetime import date
class AttendanceRequest(BaseModel):
    user_id: uuid.UUID
    attendance_date: date
    status: str = Field(..., description="Present or Absent")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "c56a4180-65aa-42ec-a945-5fd21dec0538",
                "attendance_date": "2026-03-16",
                "status": "Present"
            }
        }

class EmployeeResponse(BaseModel):
    user_id: uuid.UUID
    firstname: Optional[str]
    lastname: Optional[str]
    isactive: bool
    emailaddress: str
    department: str
    
    class Config:
        from_attributes = True


class EmployeeWithAttendance(BaseModel):
    user_id: uuid.UUID
    firstname: Optional[str]
    lastname: Optional[str]
    emailaddress: str
    department: str
    status: Optional[str]
    present_days: int
    absent_days: int
    isactive: bool
    user_company_id:str

    class Config:
        from_attributes = True


class AttendanceResponse(BaseModel):
    attendance_id: uuid.UUID
    user_id: uuid.UUID
    attendance_date: date
    status: str

    class Config:
        from_attributes = True



# ----- Database Dependency -----
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# ----- Lifespan event to create tables -----
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    async with postgres_engine.begin() as conn:
        await conn.run_sync(SQLAlchemyBase.metadata.create_all)
    yield
    # Clean up on shutdown
    await postgres_engine.dispose()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ----- API Endpoints -----
@app.post("/employee/", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def add_employees(
    employee_data: AddEmployeeSchemaRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new employee to the database with validation.
    """

    try:
        # -----------------------------
        # 1️⃣ Required field validation
        # -----------------------------
        if not employee_data.firstName or not employee_data.lastName:
            raise HTTPException(
                status_code=400,
                detail="First name and last name are required"
            )

        if not employee_data.emailAddress:
            raise HTTPException(
                status_code=400,
                detail="Email address is required"
            )

        if not employee_data.department:
            raise HTTPException(
                status_code=400,
                detail="Department is required"
            )

        # -----------------------------
        # 2️⃣ Email format validation
        # -----------------------------
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"

        if not re.match(email_regex, employee_data.emailAddress):
            raise HTTPException(
                status_code=400,
                detail="Invalid email format"
            )

        # -----------------------------
        # 3️⃣ Duplicate email check
        # -----------------------------
        query = select(User).where(User.emailaddress == employee_data.emailAddress)
        result = await db.execute(query)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise HTTPException(
                status_code=409,
                detail="Employee with this email already exists"
            )

        # -----------------------------
        # 4️⃣ Create new user
        # -----------------------------
        new_user = User(
            firstname=employee_data.firstName.strip(),
            lastname=employee_data.lastName.strip(),
            emailaddress=employee_data.emailAddress.lower().strip(),
            department=employee_data.department.strip(),
            isactive=True
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        return new_user

    except HTTPException:
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create employee: {str(e)}"
        )





@app.get("/employee/{user_id}", response_model=EmployeeResponse)
async def get_employee(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get an employee by their user_id.
    """
    from sqlalchemy import select
    
    query = select(User).where(User.user_id == user_id)
    result = await db.execute(query)
    employee = result.scalar_one_or_none()
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with id {user_id} not found"
        )
    
    return employee






@app.get("/employees/", response_model=List[EmployeeWithAttendance])
async def get_all_employees(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):

    today = date.today()

    query = (
        select(
            User.user_id,
            User.firstname,
            User.lastname,
            User.emailaddress,
            User.department,
            User.user_company_id,   
            User.isactive,  # add this

            # today's attendance status
            func.max(
                case(
                    (Attendance.attendance_date == today, Attendance.status),
                    else_=None
                )
            ).label("status"),

            # total present days
            func.sum(
                case((Attendance.status == "Present", 1), else_=0)
            ).label("present_days"),

            # total absent days
            func.sum(
                case((Attendance.status == "Absent", 1), else_=0)
            ).label("absent_days"),
        )
        .outerjoin(Attendance, Attendance.user_id == User.user_id)
        .group_by(
            User.user_id,
            User.firstname,
            User.lastname,
            User.emailaddress,
            User.department,
            User.user_company_id,
            User.isactive  # must be grouped
        )
        .offset(skip)
        .limit(limit)
    )

    result = await db.execute(query)

    employees = [
        {
            "user_id": row.user_id,
            "user_company_id" : row.user_company_id,
            "firstname": row.firstname,
            "lastname": row.lastname,
            "emailaddress": row.emailaddress,
            "department": row.department,
            "status": row.status if row.status else "Not Marked",
            "present_days": row.present_days or 0,
            "absent_days": row.absent_days or 0,
            "isactive": row.isactive
        }
        for row in result.fetchall()
    ]

    return employees





@app.put("/employee/{user_id}", response_model=EmployeeResponse)
async def update_employee(
    user_id: uuid.UUID,
    employee_data: AddEmployeeSchemaRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing employee.
    """
    from sqlalchemy import select
    
    query = select(User).where(User.user_id == user_id)
    result = await db.execute(query)
    employee = result.scalar_one_or_none()
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with id {user_id} not found"
        )
    
    try:
        # Update fields
        employee.firstname = employee_data.firstname
        employee.lastname = employee_data.lastname
        employee.emailaddress = employee_data.emailaddress
        employee.department = employee_data.department
        
        await db.commit()
        await db.refresh(employee)
        
        return employee
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update employee: {str(e)}"
        )

@app.delete("/employee/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an employee (soft delete by setting isactive to false).
    """
    from sqlalchemy import select
    
    query = select(User).where(User.user_id == user_id)
    result = await db.execute(query)
    employee = result.scalar_one_or_none()
    
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with id {user_id} not found"
        )
    
    try:
        # Soft delete by setting isactive to False
        employee.isactive = False
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete employee: {str(e)}"
        )





@app.post("/attendance/", response_model=AttendanceResponse)
async def mark_attendance(
    attendance_data: AttendanceRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        attendance = Attendance(
            user_id=attendance_data.user_id,
            attendance_date=attendance_data.attendance_date,
            status=attendance_data.status
        )

        db.add(attendance)
        await db.commit()
        await db.refresh(attendance)

        return attendance

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))




@app.get("/attendance/{user_id}", response_model=List[AttendanceResponse])
async def get_employee_attendance(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    query = select(Attendance).where(Attendance.user_id == user_id)

    result = await db.execute(query)

    records = result.scalars().all()

    return records


@app.get("/attendance/filter/")
async def filter_attendance(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, and_

    query = select(Attendance).where(
        and_(
            Attendance.attendance_date >= start_date,
            Attendance.attendance_date <= end_date
        )
    )

    result = await db.execute(query)

    return result.scalars().all()





@app.get("/attendance/present-days/{user_id}")
async def total_present_days(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, func

    query = select(func.count()).where(
        Attendance.user_id == user_id,
        Attendance.status == "Present"
    )

    result = await db.execute(query)

    total = result.scalar()

    return {
        "user_id": user_id,
        "total_present_days": total
    }




@app.get("/dashboard")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select, func

    total_users = await db.execute(select(func.count(User.user_id)))
    total_attendance = await db.execute(select(func.count(Attendance.attendance_id)))

    present = await db.execute(
        select(func.count()).where(Attendance.status == "Present")
    )

    absent = await db.execute(
        select(func.count()).where(Attendance.status == "Absent")
    )

    return {
        "total_employees": total_users.scalar(),
        "total_attendance_records": total_attendance.scalar(),
        "present_count": present.scalar(),
        "absent_count": absent.scalar()
    }







@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint to verify database connection.
    """
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}"
        )








# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)

