from app.miniapp.auth import TelegramMiniAppUser

def test_user():
    assert TelegramMiniAppUser(1,'A',None,'ru').id==1
