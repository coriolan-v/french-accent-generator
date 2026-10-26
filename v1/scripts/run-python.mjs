import { existsSync, readFileSync } from "node:fs";
import { delimiter, dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptDirectory, "..");
const environmentRoot = join(projectRoot, ".venv");
const configurationPath = join(environmentRoot, "pyvenv.cfg");
const sitePackages = join(environmentRoot, "Lib", "site-packages");

if (!existsSync(configurationPath) || !existsSync(sitePackages)) {
  console.error("The Python environment is missing. Run scripts/setup-vevo.ps1 first.");
  process.exit(1);
}

const configuration = readFileSync(configurationPath, "utf8");
const home = configuration.match(/^home\s*=\s*(.+)$/m)?.[1]?.trim();
const pythonExecutable = home ? join(home, "python.exe") : undefined;

if (!pythonExecutable || !existsSync(pythonExecutable)) {
  console.error("The base Python interpreter referenced by .venv/pyvenv.cfg could not be found.");
  process.exit(1);
}

const pythonArguments = process.argv.slice(2);
if (pythonArguments.length === 0) {
  console.error("No Python script or arguments were supplied.");
  process.exit(1);
}

const environment = { ...process.env };
delete environment.PYTHONHOME;
environment.PYTHONNOUSERSITE = "1";
environment.PYTHONUTF8 = "1";
environment.PYTHONPATH = [sitePackages, environment.PYTHONPATH].filter(Boolean).join(delimiter);
environment.Path = [home, environment.Path || environment.PATH].filter(Boolean).join(delimiter);

const child = spawn(pythonExecutable, pythonArguments, {
  cwd: projectRoot,
  env: environment,
  stdio: "inherit",
  windowsHide: true,
});

child.on("error", (error) => {
  console.error(`Could not start Python: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
