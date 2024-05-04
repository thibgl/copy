from lib import utils
from bson.objectid import ObjectId

class Database:
    def __init__(self, app):
        self.app = app
        self.partial_update = ['auth', 'detail', 'account']
        self.root_values = ['status']

    async def update(self, obj: object, update: object, collection: str) -> bool:
        current_time = utils.current_time()

        if update and len(update) > 0:
            update_format = {}
            update_format["updated"] = current_time
            update_format["updated_date"] = utils.current_readable_time()

            for key, value in update.items():
                if key in self.root_values:
                    update_format[key] = value
                else:
                    obj[key]["updated"] = current_time
                    update_format[key] = {}
                    update_format[key]["updated"] = current_time

                    if key in self.partial_update:
                        category_obj = obj[key]
                        category_data = category_obj["data"]
                        category_data.update(update[key])
                        update_format[key]["data"] = category_data
                    else:
                        obj[key]["data"] = update[key]
                        update_format[key]["data"] = obj[key]["data"]
            
            if "_id" in obj.keys():
                await self.app.db[collection].update_one({"_id": obj["_id"]}, {"$set": update_format})
            else:
                obj.update(update_format)
                await self.app.db[collection].insert_one(obj)

        return True
    
    def unpack(self, obj: object) -> object:
        unpack = {}
        for key, value in obj.items():
            # if isinstance(value, ObjectId):
            #     unpack[key] = str(value)
            if isinstance(value, dict):
                unpack[key] = value["data"]
            else:
                unpack[key] = value

        return unpack