if __name__ == "__main__":
    from src.config import config
    from src.app_entry import run_app

    config = config
    config["debug"] = True
    config["gui"] = {
        "type": "web",
        "launch_mode": "pywebview",  # default
    }
    run_app(config)
