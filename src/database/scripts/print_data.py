from tabulate import tabulate

from src.database.models import NewSolution, VSPCore, VSPAddress, VSPTimeline, VSPArea, VSPWorkplace, VSPOperations, \
    VSPProperty, ClientFlow
from src.database.service import SQLiteService


def print_database_sample(db_service: SQLiteService, limit: int = 10):
    """Выводит образцы данных из всех таблиц, включая chunks"""
    with db_service.get_session() as session:

        print("\n" + "=" * 50 + "\nЗаписи по Новым решениям:\n" + "=" * 50)
        area_report_data = session.query(NewSolution).limit(limit).all()

        if not area_report_data:
            print("Таблица  пуста")
        else:
            report_rows = []
            for record in area_report_data:
                row = {c.name: getattr(record, c.name) for c in NewSolution.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nПоследние записи из VSPCore:\n" + "=" * 50)
        vsp_core = session.query(VSPCore).limit(limit).all()

        if not vsp_core:
            print("Таблица vsp_core пуста")
        else:
            report_rows = []
            for record in vsp_core:
                row = {c.name: getattr(record, c.name) for c in VSPCore.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nПоследние записи из VSPAddress:\n" + "=" * 50)
        vsp_address = session.query(VSPAddress).limit(limit).all()

        if not vsp_address:
            print("Таблица VSPAddress пуста")
        else:
            report_rows = []
            for record in vsp_address:
                row = {c.name: getattr(record, c.name) for c in VSPAddress.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))


        print("\n" + "=" * 50 + "\nПоследние записи из VSPTimeline:\n" + "=" * 50)
        vsp_timeline = session.query(VSPTimeline).limit(limit).all()

        if not vsp_timeline:
            print("Таблица VSPTimeline пуста")
        else:
            report_rows = []
            for record in vsp_timeline:
                row = {c.name: getattr(record, c.name) for c in VSPTimeline.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nПоследние записи из VSPWorkplace:\n" + "=" * 50)
        vsp_workplace = session.query(VSPWorkplace).limit(limit).all()

        if not vsp_workplace:
            print("Таблица VSPWorkplace пуста")
        else:
            report_rows = []
            for record in vsp_workplace:
                row = {c.name: getattr(record, c.name) for c in VSPWorkplace.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nПоследние записи из VSPOperations:\n" + "=" * 50)
        vsp_operations = session.query(VSPOperations).limit(limit).all()

        if not vsp_operations:
            print("Таблица VSPOperations пуста")
        else:
            report_rows = []
            for record in vsp_operations:
                row = {c.name: getattr(record, c.name) for c in VSPOperations.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nПоследние записи из VSPProperty:\n" + "=" * 50)
        vsp_property = session.query(VSPProperty).limit(limit).all()

        if not vsp_property:
            print("Таблица VSPProperty пуста")
        else:
            report_rows = []
            for record in vsp_property:
                row = {c.name: getattr(record, c.name) for c in VSPProperty.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))

        print("\n" + "=" * 50 + "\nЗаписи по клиентопотоку:\n" + "=" * 50)
        area_report_data = session.query(ClientFlow).limit(limit).all()

        if not area_report_data:
            print("Таблица  пуста")
        else:
            report_rows = []
            for record in area_report_data:
                row = {c.name: getattr(record, c.name) for c in ClientFlow.__table__.columns}
                report_rows.append(row)

            print(tabulate(report_rows, headers="keys", tablefmt="grid"))


if __name__ == "__main__":
    db_service = SQLiteService()
    print_database_sample(db_service, limit=20)
