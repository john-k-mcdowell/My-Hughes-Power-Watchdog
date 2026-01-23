# High Level Guidance
## Planning
- First think through the problem, read the codebase for relevant files, and write a plan to tasks/todo.md.
- The plan should have a list of todo items that you can check off as you complete them

## Development
- Before you begin working, check in with me and I will verify the plan.
- begin working on the todo items, marking them as complete as you go.
- Please every step of the way just give me a high level explanation of what changes you made
- Make every task and code change you do as simple as possible. We want to avoid making any massive or complex changes. Every change should impact as little code as possible. Everything is about simplicity.
- Finally, add a review section to the todo.md file with a summary of the changes you made and any other relevant information.

## When Writing Code
- When writing code, always use a modular approach to avoid monolithic code
- Use Semantic versioning. Evaluate changes and suggest changes to version numbers
- Update version numbers before any commits
- Prompt me to accept changes and make a commit when appropriate
- This project is being done in a git repo that will be synced with GitHub.  Here are Git Commit instructions:
- All files should be included if not excluded by .gitignore
- Any database files should be excluded in .gitignore
- Any .env files should be excluded in .gitignore
- There should be two standard branches. Main and Development. Initial version should go into Main, then subsequent work goes into the development branch until the development branch is promoted to Main.
- All secrets, API keys, etc. should be stored in .env, all configuration options should be included in a config.yaml file
- Pre compile all python code to check for syntax errors

## Project Specific Instructions
- This project if for an integration in Home Assistant (HA).  
- The HA integration will use HACS to install it from a github repo.
- This project is based on work done using ESPHome rather than a HA integration.  The original ESPHome sample code and the README file for it is contained in the Original_Starting_Point FolderS