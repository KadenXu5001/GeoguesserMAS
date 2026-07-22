const sourceDatabaseName = process.env.MONGO_APP_DATABASE;
const restoredDatabaseName = process.env.RESTORE_DRILL_DATABASE || "geoguesser_restore_drill";

if (!sourceDatabaseName) throw new Error("MONGO_APP_DATABASE is required");

const source = db.getSiblingDB(sourceDatabaseName);
const restored = db.getSiblingDB(restoredDatabaseName);
const names = source.getCollectionNames()
  .filter((name) => !name.startsWith("system."))
  .sort();

const inventory = names.map((name) => {
  const sourceCollection = source.getCollection(name);
  const restoredCollection = restored.getCollection(name);
  const sourceCount = sourceCollection.countDocuments({});
  const restoredCount = restoredCollection.countDocuments({});
  const sourceSample = sourceCollection.find({}, { _id: 1 }).sort({ _id: 1 }).limit(1).toArray()[0]?._id;
  const restoredSample = restoredCollection.find({}, { _id: 1 }).sort({ _id: 1 }).limit(1).toArray()[0]?._id;
  if (sourceCount !== restoredCount || EJSON.stringify(sourceSample) !== EJSON.stringify(restoredSample)) {
    throw new Error(`restore mismatch for ${name}`);
  }
  return {
    name,
    sourceCount,
    restoredCount,
    representativeId: sourceSample ?? null,
  };
});

const extra = restored.getCollectionNames()
  .filter((name) => !name.startsWith("system.") && !names.includes(name));
if (extra.length) throw new Error(`unexpected restored collections: ${extra.join(", ")}`);

print(EJSON.stringify(inventory, { relaxed: true }));
