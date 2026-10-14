from .shell import OperatorShell


def main() -> int:
    return OperatorShell().run()


if __name__ == "__main__":
    raise SystemExit(main())
