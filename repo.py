#!/usr/bin/env python3
"""
Codebase Packaging Script for AI Training/Evaluation Licensing Submissions.

This script:
1. Fetches all remote branches and tags.
2. Runs gitleaks to check for secret leaks.
3. Creates and verifies a git bundle (`repo.bundle`).
4. Exports GitHub issues and PRs if the GitHub CLI (`gh`) is available and authenticated.
5. Packages all submission files into a single `.zip` file for upload.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Utility function to execute shell commands and handle errors."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip(), e.returncode
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", -1


def check_tool_installed(tool_name):
    """Check if a CLI tool is installed and available in PATH."""
    return shutil.which(tool_name) is not None


def fetch_all_git(repo_dir):
    """Fetch all remote branches and tags."""
    print(" Fetching all remote branches and tags...")
    stdout, stderr, code = run_command(["git", "fetch", "--all", "--tags"], cwd=repo_dir)
    if code != 0:
        print(f" Warning during git fetch:\n{stderr}")
    else:
        print(" Remote refs fetched successfully.")


def run_gitleaks_check(repo_dir):
    """Check repository history for secrets using Gitleaks."""
    print("\n Scanning repository history for secrets using Gitleaks...")
    if not check_tool_installed("gitleaks"):
        print(" Warning: 'gitleaks' is not installed or not in PATH.")
        print("   Please install gitleaks (https://github.com/gitleaks/gitleaks) to ensure no secrets are leaked.")
        response = input("Do you want to proceed without secret scanning? (y/N): ").strip().lower()
        if response != 'y':
            print("Aborting submission packaging.")
            sys.exit(1)
        return

    _, stderr, code = run_command(["gitleaks", "git", "-v", "."], cwd=repo_dir, check=False)
    if code != 0:
        print("\n Secret Leak Check Failed!")
        print("Gitleaks detected potential secrets or credentials in your history.")
        print("Details:\n", stderr)
        print("\n Please revoke any leaked keys and purge them from git history before packaging.")
        sys.exit(1)
    else:
        print(" Secret scan passed: No secrets detected.")


def create_git_bundle(repo_dir, bundle_path):
    """Create and verify the git bundle."""
    print("\n Creating git bundle...")
    cmd_create = ["git", "bundle", "create", str(bundle_path), "--all"]
    _, stderr, code = run_command(cmd_create, cwd=repo_dir)
    if code != 0:
        print(f" Failed to create git bundle:\n{stderr}")
        sys.exit(1)

    print(f" Bundle created at: {bundle_path}")

    print(" Verifying git bundle...")
    cmd_verify = ["git", "bundle", "verify", str(bundle_path)]
    stdout, stderr, code = run_command(cmd_verify, cwd=repo_dir)
    if code != 0:
        print(f" Bundle verification failed:\n{stderr}")
        sys.exit(1)

    print(" Bundle verified successfully.")


def export_github_data(repo_dir, issues_path, prs_path):
    """Export issues and PRs using GitHub CLI if available."""
    if not check_tool_installed("gh"):
        print("\n GitHub CLI ('gh') not found. Skipping issues/PRs export.")
        print("   (Optional) Install 'gh' and run 'gh auth login' to include issues & PRs.")
        return False

    print("\n Exporting GitHub Issues and Pull Requests...")

    # Export Issues
    cmd_issues = [
        "gh", "issue", "list",
        "--state", "all",
        "--limit", "10000",
        "--json", "number,title,body,author,createdAt,closedAt,labels,comments"
    ]
    stdout, stderr, code = run_command(cmd_issues, cwd=repo_dir, check=False)
    if code == 0:
        with open(issues_path, "w", encoding="utf-8") as f:
            f.write(stdout)
        print(f" Exported issues to {issues_path.name}")
    else:
        print(f" Could not export issues (Ensure gh is authenticated and remote is GitHub):\n{stderr}")

    # Export PRs
    cmd_prs = [
        "gh", "pr", "list",
        "--state", "all",
        "--limit", "10000",
        "--json", "number,title,body,author,createdAt,mergedAt,closedAt,baseRefName,headRefName,comments,reviews"
    ]
    stdout, stderr, code = run_command(cmd_prs, cwd=repo_dir, check=False)
    if code == 0:
        with open(prs_path, "w", encoding="utf-8") as f:
            f.write(stdout)
        print(f" Exported pull requests to {prs_path.name}")
    else:
        print(f" Could not export pull requests:\n{stderr}")

    return issues_path.exists() or prs_path.exists()


def package_submission(output_dir, zip_filename, files_to_zip):
    """Compress the bundle and optional export files into a single ZIP file."""
    zip_path = output_dir / zip_filename
    print(f"\n Creating final submission package: {zip_path.name}...")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files_to_zip:
            if file.exists():
                zipf.write(file, arcname=file.name)
                print(f"   Added {file.name}")

    print(f"\n Packaging Complete!")
    print(f" Upload file: {zip_path.resolve()}")


def main():
    # Use current working directory or pass path as first argument
    repo_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()

    if not (repo_dir / ".git").is_dir():
        print(f" Error: '{repo_dir}' is not a valid Git repository.")
        sys.exit(1)

    print(f"Target Repository: {repo_dir}")

    # Define temporary output filenames
    bundle_file = repo_dir / "repo.bundle"
    issues_file = repo_dir / "issues.json"
    prs_file = repo_dir / "prs.json"
    submission_zip = "codebase_submission.zip"

    try:
        # Step 1: Fetch all remote tags and branches
        fetch_all_git(repo_dir)

        # Step 2: Scan for secrets
        run_gitleaks_check(repo_dir)

        # Step 3: Bundle and verify git history
        create_git_bundle(repo_dir, bundle_file)

        # Step 4: Export GitHub metadata (Issues & PRs) if possible
        exported = export_github_data(repo_dir, issues_file, prs_file)

        # Step 5: Zip deliverables together
        files_to_package = [bundle_file]
        if exported:
            if issues_file.exists():
                files_to_package.append(issues_file)
            if prs_file.exists():
                files_to_package.append(prs_file)

        package_submission(repo_dir, submission_zip, files_to_package)

    finally:
        # Clean up temporary standalone export files (leaving the packaged .zip intact)
        for temp_file in [bundle_file, issues_file, prs_file]:
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except OSError:
                    pass


if __name__ == "__main__":
    main()
