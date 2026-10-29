const { execFileSync } = require("node:child_process");

const run = (args, options = {}) =>
  execFileSync("git", args, { encoding: options.encoding || "utf8", ...options });

const output = run(["ls-tree", "-rz", "--name-only", "origin/main"], {
  encoding: "buffer"
});

const paths = output.toString("utf8").split("\0").filter(Boolean);
const suspicious = paths.filter(p =>
  p.includes("\n") ||
  p.includes("\r") ||
  p.length > 200 ||
  /content.*import axios|\.js\\ncontent/.test(p)
);

console.log("Total paths in origin/main:", paths.length);
console.log("Suspicious paths found:", suspicious.length);

for (const p of suspicious) {
  console.log("\nSuspicious path (first 180 characters):");
  console.log(JSON.stringify(p.slice(0, 180)));
}

if (suspicious.length === 0) {
  console.log("\nNo suspicious paths detected. No changes made.");
}
