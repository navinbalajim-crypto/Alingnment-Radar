const { execFileSync } = require("child_process");

function git(args, input) {
  return execFileSync("git", args, {
    input,
    encoding: null,
    maxBuffer: 64 * 1024 * 1024
  });
}

function gitText(args, input) {
  return git(args, input).toString("utf8").trim();
}

const parent = gitText(["rev-parse", "origin/main"]);
const rootTree = gitText(["rev-parse", parent + "^{tree}"]);

function readTree(treeOid, prefix = "") {
  const records = git(["ls-tree", "-z", treeOid])
    .toString("utf8")
    .split("\0")
    .filter(Boolean);

  const entries = [];

  for (const record of records) {
    const tab = record.indexOf("\t");
    if (tab < 0) throw new Error("Invalid Git tree record");

    const metadata = record.slice(0, tab);
    const name = record.slice(tab + 1);
    const match = metadata.match(
      /^(\d+) (blob|tree|commit) ([0-9a-f]{40,64})$/
    );

    if (!match) throw new Error("Invalid metadata: " + metadata);

    const [, mode, type, oid] = match;
    const path = prefix ? prefix + "/" + name : name;

    entries.push({
      mode,
      type,
      oid,
      name,
      path,
      children: type === "tree" ? readTree(oid, path) : null
    });
  }

  return entries;
}

const entries = readTree(rootTree);
const removed = [];

function filterTree(items) {
  return items.filter(item => {
    if (item.type === "tree") {
      item.children = filterTree(item.children);
      return true;
    }

    if (
      item.path.startsWith("frontend/src/services/apiClient.js") &&
      item.path !== "frontend/src/services/apiClient.js"
    ) {
      removed.push(item.path);
      return false;
    }

    return true;
  });
}

const filtered = filterTree(entries);

if (removed.length !== 1) {
  throw new Error(
    "Expected one malformed entry; found " + removed.length
  );
}

function writeTree(items) {
  const records = items.map(item => {
    const oid = item.type === "tree"
      ? writeTree(item.children)
      : item.oid;

    return `${item.mode} ${item.type} ${oid}\t${item.name}\0`;
  });

  return gitText(
    ["mktree", "-z"],
    Buffer.from(records.join(""), "utf8")
  );
}

const newTree = writeTree(filtered);

const commit = gitText(
  ["commit-tree", newTree, "-p", parent],
  Buffer.from(
    "Repair malformed Git tree entry\n\nRemove one malformed path while preserving other entries.\n",
    "utf8"
  )
);

const verify = readTree(
  gitText(["rev-parse", commit + "^{tree}"])
);

const actualPaths = [];

function collect(items) {
  for (const item of items) {
    if (item.type === "tree") {
      collect(item.children);
    } else {
      actualPaths.push(item.path);
    }
  }
}

collect(verify);

if (!actualPaths.includes("frontend/src/services/apiClient.js")) {
  throw new Error("Legitimate apiClient.js is missing");
}

if (
  actualPaths.some(path =>
    path.startsWith("frontend/src/services/apiClient.js") &&
    path !== "frontend/src/services/apiClient.js"
  )
) {
  throw new Error("Malformed path remains");
}

if (gitText(["rev-parse", commit + "^"]) !== parent) {
  throw new Error("Parent commit verification failed");
}

console.log("\n===== REPAIR COMMIT CREATED =====");
console.log("Original commit:", parent);
console.log("Repair commit:", commit);
console.log("Malformed entries removed:", removed.length);
console.log("Legitimate apiClient.js preserved: YES");
console.log("Parent commit verified: YES");
console.log("Nothing pushed. Current branch unchanged.");