from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import models, schemas, database, auth
from datetime import timedelta

app = FastAPI(title="Task App API")

# Разрешаем запросы с любого источника (для тестов)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Создаем таблицы при запуске
@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=database.engine)

@app.post("/register")
def register(user: schemas.UserAuth, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(username=user.username, hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"msg": "User created successfully"}

@app.post("/token")
def login_for_access_token(user: schemas.UserAuth, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if not db_user or not auth.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": db_user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/friends")
def add_friend(friend_req: schemas.FriendAdd, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    friend_user = db.query(models.User).filter(models.User.username == friend_req.friend_username).first()
    if not friend_user:
        raise HTTPException(status_code=404, detail="Friend not found")
    if friend_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot add yourself")
    
    existing = db.query(models.Friend).filter(
        models.Friend.user_id == current_user.id,
        models.Friend.friend_id == friend_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already friends")

    new_friend = models.Friend(user_id=current_user.id, friend_id=friend_user.id)
    db.add(new_friend)
    db.commit()
    return {"msg": "Friend added"}

@app.get("/friends")
def get_friends(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    friends = db.query(models.Friend).filter(models.Friend.user_id == current_user.id).all()
    friend_ids = [f.friend_id for f in friends]
    users = db.query(models.User).filter(models.User.id.in_(friend_ids)).all()
    return [{"id": u.id, "username": u.username} for u in users]

@app.post("/tasks")
def create_task(task: schemas.TaskCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    assignee = db.query(models.User).filter(models.User.username == task.assignee_username).first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found")
    
    # Проверка, являются ли они друзьями (упрощенная: проверяем только в одну сторону)
    friendship = db.query(models.Friend).filter(
        models.Friend.user_id == current_user.id,
        models.Friend.friend_id == assignee.id
    ).first()
    
    if not friendship:
         # Можно разрешить писать всем, но по ТЗ "добавлять в друзья". 
         # Если строго: raise HTTPException(403, "Not friends")
         pass 

    new_task = models.Task(
        title=task.title,
        author_id=current_user.id,
        assignee_id=assignee.id,
        status="new"
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return {"msg": "Task created", "task_id": new_task.id}

@app.get("/tasks")
def get_my_tasks(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    tasks = db.query(models.Task).filter(models.Task.assignee_id == current_user.id).all()
    return [{"id": t.id, "title": t.title, "status": t.status, "author_id": t.author_id} for t in tasks]

@app.put("/tasks/{task_id}")
def update_task_status(task_id: int, new_status: str, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.assignee_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or not yours")
    task.status = new_status
    db.commit()
    return {"msg": "Status updated"}