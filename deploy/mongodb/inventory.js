const databaseName = process.env.INVENTORY_DATABASE || process.env.MONGO_APP_DATABASE;
if (!databaseName) throw new Error("INVENTORY_DATABASE or MONGO_APP_DATABASE is required");

const target = db.getSiblingDB(databaseName);
const inventory = target.getCollectionNames()
  .filter((name) => !name.startsWith("system."))
  .sort()
  .map((name) => {
    const collection = target.getCollection(name);
    const representativeId = collection.find({}, { _id: 1 }).sort({ _id: 1 }).limit(1).toArray()[0]?._id;
    return {
      name,
      count: collection.countDocuments({}),
      representativeId: representativeId ?? null,
    };
  });

print(EJSON.stringify({ database: databaseName, collections: inventory }, { relaxed: true }));
