from lib import utils

indexes = {
    "users": {},

}

class Database:
    def __init__(self, app):
        self.app = app
        self.partial_update = ['auth', 'detail', 'account']

    async def update(self, obj: object, update: object, collection: str) -> bool:
        current_time = utils.current_time()

        if update:
            update_format = {}
            update_format["updated"] = current_time
            update_format["updated_date"] = utils.current_readable_time()
            for category_key in update.keys():
                update_format[category_key] = {}
                category_obj = obj[category_key]
                category_obj["updated"] = current_time
                category_data = category_obj["data"]
                
                if category_key in self.partial_update:
                    category_data.update(update[category_key])
                    update_format[category_key]["data"] = category_data
                else:
                    obj[category_key]["data"] = update[category_key]
                    update_format[category_key]["data"] = obj[category_key]["data"]
            
            # print(update)
            if "_id" in obj.keys():
                await self.app.db[collection].update_one({"_id": obj["_id"]}, {"$set": update_format})
            else:
                await self.app.db[collection].insert_one(obj)

        return True