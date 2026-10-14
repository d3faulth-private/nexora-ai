from alembic import command
from alembic.config import Config


def main() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    print("Nexora database is at the latest migration.")


if __name__ == "__main__":
    main()
