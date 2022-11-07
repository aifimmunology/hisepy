''' A script used to export a csv from a pytest_metrics output.
See for more info: https://pytest-monitor.readthedocs.io/en/latest/run.html
'''
import sqlite3
import os
import pandas as pd


class Metrics_db:

    def __init__(self):
        self.output_filename = 'hisepy_pytest_metrics.csv'
        self.metrics_cols = [
            'ITEM', 'ITEM_VARIANT', 'ITEM_FS_LOC', 'KIND', 'TOTAL_TIME',
            'USER_TIME', 'KERNEL_TIME', 'CPU_USAGE', 'MEM_USAGE'
        ]
        self.db_input_file = '.pymon'

    def conn_local_db(self):
        ''' connects to a local db file
        '''
        conn = sqlite3.connect('%s/%s' % (os.getcwd(), self.db_input_file),
                               detect_types=sqlite3.PARSE_COLNAMES)
        return conn

    def get_metrics_query(self):
        ''' Returns the query string for metrics db file 
        '''
        return "SELECT * FROM TEST_METRICS;"

    def export_csv(self, conn):
        ''' export the db file to csv to working directory 
        '''
        keep_cols = self.metrics_cols
        db_df = pd.read_sql_query(self.get_metrics_query(), conn)
        db_filepath = '%s/%s' % (os.getcwd(), self.output_filename)
        db_df.to_csv(db_filepath, index=False, columns=self.metrics_cols)
        print("CPU & Memory usage unit test metrics saved to: %s/%s" %
              (os.getcwd(), self.output_filename))


if __name__ == "__main__":
    this_instance = Metrics_db()
    conn = this_instance.conn_local_db()
    this_instance.export_csv(conn)
