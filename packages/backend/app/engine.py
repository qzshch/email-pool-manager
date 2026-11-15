""" 平台引擎注册 """
from .platforms.mail_tm.engine import MailTmEngine
from .platforms.openai.engine import OpenAIEngine
from .platforms.registry import registry
from .platforms.tempmail_lol.engine import TempmailLolEngine

openai_engine = OpenAIEngine()
registry.register(openai_engine)

# 邮箱平台：批量创建临时邮箱并自动入池
mail_tm_engine = MailTmEngine()
registry.register(mail_tm_engine)

tempmail_lol_engine = TempmailLolEngine()
registry.register(tempmail_lol_engine)
