import csv
import os

def main():
    with open('invoices.csv', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            print(row['name'] + ", " + row['article_name'])

    return 

if __name__ == "__main__":
    main()