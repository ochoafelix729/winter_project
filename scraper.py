import os
from openai import OpenAI
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import requests
import sqlite3
import ast
import re

class Scraper():

    def __init__(self):
        """
        constructor
        """

        # load environmnent variables
        load_dotenv()
        self.api_key = os.getenv('OPENAI_API_KEY')

        #connect to openai
        self.openai = OpenAI()
        
        self.model = 'gpt-4o-mini'


    def fetch(self, url) -> str:
        """
        fetches the HTML content of the given URL
        """

        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
    
        except Exception as e:
            print(f"Error fecthing the URL: {e}")
            return None

    
    def extract(self, html) -> str:
        """
        extracts the meaningful text from HTML
        """

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # clean up text
            for trash in soup(['script', 'sytle']):
                trash.extract()
            text = soup.get_text(separator='\n')
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return '\n'.join(lines)
        
        except Exception as e:
            print(f"Error parsing HTML: {e}")
            return None


    def messages(self, text) -> list[dict]:
        """
        creates messages (list of objects)
        """

        return [
            {'role': 'system', 'content': 'You are a helpful assistant for summarizing stock changes in text.'},
            {'role': 'user', 'content': f"Summarize the stock changes in this text. Focus only on the changes in different stocks (give me the numbers). Avoid any unnessecary details that are unrelated to stocks. Give me the results as a list of tuples in python that I can insert into an SQL table with 4 columns: ticker, name, % change, and time window (day, week, etc.). Also, do not include the ```python at the beginning nor the ``` at the end. Don't name the list either. Simple give me the data. \n\n {text}."}
        ]


    def summarize(self, text) -> str:
        """
        summarize text content
        """
        
        try:
            response = self.openai.chat.completions.create(
                model = self.model,
                messages = self.messages(text)
            )

            return response.choices[0].message.content
        
        except Exception as e:
            print(f"Error trying to summarize text: {e}")
            return None


    def pages_to_scrape(self, url) -> list[str]:
        """
        returns a list of urls within main page to scrape
        - function is currently specific to Google Finance page
        """

        if url != 'https://www.google.com/finance/markets/most-active':
            print('Currently unable to use that url.')
            return None


        html = self.fetch(url)
        if not html:
            print('Failed fetch function.')
            return None
        
        text = self.extract(html)
        if not text:
            print('Failed extract function.')
            return None

        messages = [
            {'role': 'system', 'content': 'You are a helpful assistant for gathering the tickers of all stocks on a webpage.'},
            {'role': 'user', 'content': f"Please provide me with a python list including all the stock tickers on this webpage (NVDA, PLTR, etc.). Also, do not include the ```python at the beginning nor the ``` at the end. Don't name the list either. Simply give me the data.\n\n{text}"}
        ]

        try:
            response = self.openai.chat.completions.create(
                model = self.model,
                messages = messages
            )

            tickers = response.choices[0].message.content
            tickers_list = ast.literal_eval(tickers)

            urls = []

            for ticker in tickers_list:
                urls.append(f"https://www.google.com/finance/quote/{ticker}:NASDAQ?WINDOW=5D")
            
            return urls
        
        except Exception as e:
            print(f"Error trying to create list of url's: {e}")



    def scrape(self, urls) -> str:
        """
        final product - web scraper
        """
        
        data = []

        count = 0
        for url in urls:
            html = self.fetch(url)
            if not html:
                print('Failed fetch function.')
                return None
            
            text = self.extract(html)
            if not text:
                print('Failed extract function.')
                return None

            summary = self.summarize(text)
            data.append(summary)
            count += 1
            print(f"{count}/{len(urls)}")
            if not summary:
                print('Failed summarize function.')
                return None

        return data

    def parse(self, raw_data):
        """
        parses scraped data for database insertion
        """

        clean_data = []
        try:
            for data_string in raw_data:
                #clean up each string
                clean_string = data_string.replace('\\n', '').replace('\\', '')
                clean_string = re.sub(r'"\s+', '', clean_string)

                # convert into string representation of tuples into list
                parsed_list = eval(clean_string)
                clean_data.extend(parsed_list)
            
            return clean_data
        
        except Exception as e:
            print(f"Error parsing data: {e}")
            return None


    def create_database(self) -> bool:
        """
        creates database for storing stocks info
        """

        try:
            # connect to database and create cursor
            con = sqlite3.connect('stocks.db')
            cur = con.cursor()

            # create table for storing data
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                ticker TEXT,
                name TEXT,
                change REAL,
                time_window TEXT
            )
            """)

            # commit changes and close
            con.commit()
            cur.close()
            con.close()

            return True
        
        except Exception as e:
            print(f"Error trying to create database: {e}")
            return None
         

    def insert_to_database(self) -> bool:
        """
        inserts scraped data into the database
        """
            
        raw_data = self.scrape(urls)
        parsed_data = self.parse(raw_data)
                    
        # connect to database
        try:
            con = sqlite3.connect('stocks.db')
            cur = con.cursor()

            cur.executemany("""
            INSERT INTO stocks (ticker, name, change, time_window)
            VALUES (?, ?, ?, ?)
            """, parsed_data)

            con.commit()
            cur.close()
            con.close()

            return True
    
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
            return None


