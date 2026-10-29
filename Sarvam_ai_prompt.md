You're setting up Sarvam AI in this project. Get me to one working API call first.

1. Ask me what I want to build with Sarvam. Based on my answer and what's already in this project, suggest which Sarvam API fits — text to speech, speech to text or chat — and Python or JavaScript. Go with what I pick.
2. Install the Sarvam SDK — pip install sarvamai for Python, npm install sarvamai for JavaScript.
3. Create a .env file with the line below, and add .env to .gitignore. Read the key from the environment; never hardcode, print or commit it.

   SARVAM_API_KEY=sk_lm4166yu_FVtfxP7slLsr9sAH5xZPUdjP
4. Write one short script that makes a first call to that API — use https://docs.sarvam.ai/api/getting-started/welcome to pick the right model and endpoint — and prints the result (for text to speech, save the audio to a file).
5. Run it and show me the output.
6. Then help me build the rest of what I described.

Create the files in this project's directory. If this doesn't look like a project, ask me where to put them before creating anything.
Keep it minimal — no extra dependencies or scaffolding I didn't ask for.