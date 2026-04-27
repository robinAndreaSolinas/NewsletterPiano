from flask_login import UserMixin
import datetime


class User(UserMixin):
    def __init__(self, id:int, email:str, password_hash:str, username:str):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.role = ['user']
        self.active = True
        self.created_at = datetime.datetime.now()
        self.updated_at = datetime.datetime.now()

    @staticmethod
    def get(user_id):
        # cerca nel DB per id, ritorna User o None
        ...