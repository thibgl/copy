class Database():
    def __init__(self, app):
        self.app = app

    async def get_all(self, collection_name):
        objects = []
        all_objects = self.app.db[collection_name].find()

        async for object in all_objects:
            objects.append(object)

        return objects
    
