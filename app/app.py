import os
import time
import json
import apprise
import requests
import schedule
from loguru import logger
from datetime import datetime


from sqliteconnector import SqliteConnector


class Monitor():
    def __init__(self):
        self.token = os.getenv("CF_TOKEN")
        self.account_id = os.getenv("CF_ACCOUNT_ID") 
        self.url = "https://api.cloudflare.com/client/v4/accounts/" + self.account_id + "/cfd_tunnel?is_deleted=false"
        self.headers = {"Authorization": "Bearer " + self.token}   
        self.connector = SqliteConnector()  
        self.connector.create_tables()
        self.notifires = os.getenv("NOTIFIERS")
        self.apobj = apprise.Apprise()
        self.init_notifires()


    def init_notifires(self):
            if len(self.notifires)!=0:
                logger.debug("Setting Apprise notification channels")
                jobs=self.notifires.split()
                for job in jobs:
                    logger.debug("Adding: " + job)
                    self.apobj.add(job)

    def send_notification(self, title, message):
        if len(self.notifires)!=0:
            self.apobj.notify(
                body=message,
                title=title,
            )


    def check_tunnels_status(self):
        try:
            logger.info("Checking Tunnels Status")
            response = requests.get(monitor.url,headers = monitor.headers)
            if response.status_code == 200:
                for t in response.json()["result"]:
                    TunnelId = str(t["id"])
                    CurrentTunnelState = t["status"]
                    LastChanged = datetime.now()
                    if not self.connector.is_tunnel_monitored(TunnelId):
                        self.connector.add_monitored_tunnel(TunnelId,CurrentTunnelState,LastChanged)
                    else:
                        TunnelState = self.connector.get_monitored_tunnel_by_id(TunnelId)[0][1]
                        if CurrentTunnelState == "healthy":
                            icon = "✅"
                        else:
                            icon = "❌"
                        if(CurrentTunnelState != TunnelState):
                            self.send_notification(
                                title="Tunnel status changed",
                                message = icon + " The tunnel " + t["name"] + " Status changed from " + TunnelState +" to " + CurrentTunnelState + " " + icon
                            )
                            self.connector.update_tunnel_state(TunnelId,CurrentTunnelState,LastChanged)
            else:
                logger.error(f"Error login to cloudflare api with status code {str(response.status_code)} \n {response.text}")
        except Exception as e:
            logger.error("Error chacking tunnels state: " + str(e))
            



if __name__ == "__main__":
   monitor = Monitor()
   schedule.every(int(os.getenv("CHECK_INTERVALS"))).seconds.do(monitor.check_tunnels_status)

   while True:
    schedule.run_pending()
    time.sleep(1)
