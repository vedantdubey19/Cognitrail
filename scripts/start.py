import uvicorn
from app.config import Settings

if __name__=='__main__':
    import os
    os.umask(0o077)
    settings = Settings()
    uvicorn.run('app.main:app',host='0.0.0.0' if settings.deployment == 'private' else '127.0.0.1',port=8100,proxy_headers=False,
                workers=1,limit_concurrency=12,timeout_keep_alive=5,access_log=False)
