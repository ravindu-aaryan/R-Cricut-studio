from flask import Flask


def register_blueprints(app: Flask) -> None:
    from . import assets, exports, imports, jobs, layouts, photos, projects, stickers, system, themes

    for mod in (system, projects, photos, stickers, themes, assets, layouts, exports, jobs, imports):
        app.register_blueprint(mod.bp)
