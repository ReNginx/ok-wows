"""Keep cleanup alive until both companion applications have exited."""


def run_app(config):
    from ok import OK, og

    app = OK(config)
    try:
        app.start()
    finally:
        app.exit_event.set()
        lifecycle = getattr(getattr(og, 'my_app', None), 'lifecycle', None)
        if lifecycle is not None:
            lifecycle.shutdown()
