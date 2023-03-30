import sqlite3
from sqlite3 import Error
from loguru import logger

class SqliteConnector:
    def __init__(self):
        self.db_file = "db/cf.db"
        self.conn = None

    def open_connection(self):
        try:
            self.conn = sqlite3.connect(self.db_file)
        except Error as e:
            logger.error(str(e))

    def close_connection(self):
        try:
            self.conn.close()
        except Error as e:
            logger.error(str(e))

    def create_tables(self):
        self.open_connection()
        create_monitored_tunnels_table = """ CREATE TABLE IF NOT EXISTS monitored_tunnels (
                                    TunnelId text PRIMARY KEY,
                                    CurrentTunnelState text NOT NULL,
                                    LastChanged datetime NOT NULL
                                ); """


        try:
            c = self.conn.cursor()
            c.execute(create_monitored_tunnels_table) 
            c.close()
            self.conn.close()          
        except Error as e:
            logger.error(str(e))
   


    def add_monitored_tunnel(self, TunnelId,CurrentTunnelState,LastChanged):
        try:
            Tunnel = (TunnelId,CurrentTunnelState,LastChanged)
            self.open_connection()
            sql =  """ INSERT INTO monitored_tunnels(TunnelId,CurrentTunnelState,LastChanged) VALUES (?,?,?)"""
            cur = self.conn.cursor()
            cur.execute(sql,Tunnel)
            self.conn.commit()
            self.conn.close()
            return str(cur.lastrowid>0), "Tunnel addedd successfully"
        except Error as e:
            logger.error(str(e))
            return False, str(e)

    def update_tunnel_state(self, TunnelId,CurrentTunnelState,LastChanged):
        try:
            self.open_connection()
            sql = ''' UPDATE monitored_tunnels
              SET CurrentTunnelState = ? ,
                  LastChanged = ?
              WHERE TunnelId = ?'''
            cur = self.conn.cursor()
            cur.execute(sql,(CurrentTunnelState,LastChanged,TunnelId))
            self.conn.commit()
            cur.close()
            self.conn.close()
            return True
        except Error as e:
            logger.error(str(e))
            return False

    def is_tunnel_monitored(self, TunnelId):
        try:
            self.open_connection()
            cursor = self.conn.cursor()
            query = "SELECT * FROM monitored_tunnels where TunnelId = '" + TunnelId + "'"
            cursor.execute(query)
            rows = [dict((cursor.description[i][0], value) \
               for i, value in enumerate(row)) for row in cursor.fetchall()]
            return (True if rows else False)
        except Exception as e:
            self.conn.close()
            logger.error(e)
            return False

    def get_monitored_tunnel_by_id(self, TunnelId):
        try:
            self.open_connection()
            cursor = self.conn.cursor()
            query = "SELECT * FROM monitored_tunnels where TunnelId = '" + TunnelId + "'"
            cursor.execute(query)
            rows = cursor.fetchall()
            return rows
        except Exception as e:
            self.conn.close()
            logger.error(e)
            return None






if __name__ == "__main__":
    con = SqliteConnector()
    con.create_tables()
