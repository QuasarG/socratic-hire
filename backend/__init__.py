# 包入口统一加载 .env，保证脚本/服务两种入口都能拿到 API Key
from dotenv import load_dotenv

load_dotenv()
