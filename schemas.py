from pydantic import BaseModel

class UserAuth(BaseModel):
    username: str
    password: str

class FriendAdd(BaseModel):
    friend_username: str

class TaskCreate(BaseModel):
    title: str
    assignee_username: str