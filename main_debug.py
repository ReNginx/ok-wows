from src.app_entry import run_app
from src.config import config

if __name__ == '__main__':
    config['debug'] = True
    run_app(config)
