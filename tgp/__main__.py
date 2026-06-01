from tgp.cli import CLI
import sys

def main():
    cli = CLI()
    sys.exit(cli.run(sys.argv[1:]))

if __name__ == "__main__":
    main()