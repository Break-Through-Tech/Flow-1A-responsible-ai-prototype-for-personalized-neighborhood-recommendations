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
        print('CSV files:')
        for i in range(len(self.pd_arr)):
            name = os.path.basename(self.list_paths[i])
            print(name)

    # Prints the number of rows, columns, and data types for each CSV file
    def listInfo(self):
        print('--------------------------')
        for i in range(len(self.pd_arr)):
            name = os.path.basename(self.list_paths[i])
            print(name + ': ')
            print('\tColumns: ', self.pd_arr[i].shape[1]) 
            print('\tRows: ', self.pd_arr[i].shape[0])
            print('Data Type: \n', self.pd_arr[i].dtypes)
            print()

    ## checks that the following zip codes are found in each file
    def zipCodesConfirmation(self):
        print('------------------------')
        print('ZipCodes Found:')
        zipCode = [33127, 33128, 33130]
        for i in range(len(self.list_paths)):
            df = self.pd_arr[i]
            name = os.path.basename(self.list_paths[i])
            found = set()
            for i in df['zip']:
                if i in zipCode:
                    found.add(i)
            print(name, " ", len(found) == len(zipCode))
            


data = validate_data('data')
data.listFileNames()
data.listInfo()
data.zipCodesConfirmation()