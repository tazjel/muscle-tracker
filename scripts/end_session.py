import os

def end_session():
    print("\n--- [ENDING SESSION] Generating Summary ---")
    
    # 1. Gather all GEMINI_*.md task files
    task_files = [f for f in os.listdir('.') if f.startswith('GEMINI_') and f.endswith('.md')]
    task_files.sort()
    
    done = []
    pending = []
    
    for tf in task_files:
        if os.path.isfile(tf):
            try:
                with open(tf, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        clean = line.strip()
                        if '[x]' in clean.lower() or '~~' in clean:
                            done.append(clean)
                        elif '[ ]' in clean:
                            pending.append(clean)
            except:
                pass
    
    # 2. Get recent git commits (Gemini specific)
    try:
        commits = os.popen('git log -n 5 --oneline').read().splitlines()
        gemini_commits = [c for c in commits if 'gemini:' in c.lower()]
    except:
        gemini_commits = []

    # 3. Create the summary
    summary = [
        '# SESSION SUMMARY',
        '',
        '## Done',
    ]
    
    if gemini_commits:
        summary.append('- **Recent Commits:**')
        for gc in gemini_commits:
            summary.append('  - ' + gc)
    
    if done:
        for d in done:
            summary.append('- ' + d)
    else:
        summary.append('- No specific tasks marked as done.')

    summary.extend([
        '',
        '## Pending',
    ])
    
    if pending:
        for p in pending:
            summary.append('- ' + p)
    else:
        summary.append('- No pending tasks in current task sheets.')

    summary.extend([
        '',
        '## Next Steps',
        '- Continue with the next available task sheet.',
        '- Review Sonnet\'s updates.',
    ])
    
    with open('SESSION_SUMMARY.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(summary))
    
    print("SESSION_SUMMARY.md has been generated. Farewell!\n")

if __name__ == '__main__':
    end_session()
