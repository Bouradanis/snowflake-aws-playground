async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }

  const toolArgs = JSON.parse(Buffer.concat(chunks).toString());

  // Extract the file path Claude is trying to read
  const readPath =
    toolArgs.tool_input?.file_path || toolArgs.tool_input?.path || "";

  // Block the .env file and the credential.py module referenced by
  // coursera/Module_3/3_snowpark_ml_modeling_code.py — both hold live credentials.
  if (readPath.includes('.env') || readPath.includes('credential.py')) {
    console.error("You cannot read credential files (.env / credential.py)");
    process.exit(2);
  }
}

main();