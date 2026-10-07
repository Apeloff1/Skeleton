import json
GAME = json.loads(r'''{"game": "Studio", "files": []}''')
def main():
    print('=== ' + GAME['game'] + ' — GameForge native build ===')
    print('gamefiles:', ', '.join(GAME['files']) or '(none)')
    print('Runtime OK.')
if __name__ == '__main__':
    main()
