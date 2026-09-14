import pandas as pd
import os 

class validate_data:
    # Initializes the class using the folder location containing the data files
    def __init__(self, dataLocation : str):
        self.files = os.listdir(dataLocation)
        self.list_paths = [os.path.join('data', file) for file in self.files if file.endswith('.csv')]
        self.pd_arr = [pd.read_csv(i) for i in self.list_paths]

    # Prints the names of all CSV files in the data folder
    def listFileNames(self):
        print('cvs files:')
        for i in self.list_paths:
            print(i.replace('data\\', ''))

    # Prints the number of rows, columns, and data types for each CSV file
    def listInfo(self):
        print('--------------------------')
        for i in range(len(self.pd_arr)):
            name = self.list_paths[i].replace('data\\', '')
            print(name + ': ')
            print('Columns: ', self.pd_arr[i].shape[0]) 
            print('Rows ', self.pd_arr[i].shape[1])
            print('Data Type: \n', self.pd_arr[i].dtypes.unique())
            print()

    ## checks that the following zip codes are found in each file
    def zipCodesConfirmation(self):
        print('------------------------')
        print('ZipCodes Found:')
        zipCode = [33127, 33128, 33130]
        for i in range(len(self.list_paths)):
            df = self.pd_arr[i]
            name = self.list_paths[i].replace('data\\', '')
            print(name, df['zip'].isin(zipCode).any())
            


data = validate_data('data')
data.listFileNames()
data.listInfo()
data.zipCodesConfirmation()