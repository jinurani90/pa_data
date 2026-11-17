### #3.Predict which Dublin Bikes stations will have 2 or fewer bicycles available within the next 60 minutes, to help prioritise bicycle redistribution?

 -identify potential bicycle shortages in advance, allowing operators to prioritise stations for rebalancing vans.
 Data Source : Official DublinBikes GBFS API,Open-Meteo Weather API
 
#### Current progress:
1. Bicycle availability data: Started fetching live bicycle availability data for approximately 115 DublinBikes stations Dublin, using the official GBFS API.
2. Weather data: Also fetching weather information using the Open-Meteo API to investigate whether weather conditions may influence bicycle availability.
3. Data storage: Started storing timestamped data snapshots in CSV files for subsequent data cleaning, analysis and  learning.
#### Next Action Plan
##### 1. Validate and Prepare CSV Data
   - Check for missing values, duplicate records and incorrect timestamps.
   - Validate weather records and timestamp alignment.
   - Combine daily CSV files into a clean dataset.
   - Prepare the data for SQLite import.
##### 2. Build the SQLite Database
    - Create an SQLite database to store the collected data.
    - Import the cleaned CSV data.
    - Add appropriate constraints to prevent duplicate records.
    - Verify database records and relationships.
##### 3. Perform Exploratory Data Analysis (EDA)

###### A. Bicycle availability by station
   - Analyse bicycle availability across individual stations.
   - Compare stations based on average and minimum bicycle availability.
   - Identify stations with consistently high or low availability.
###### B. Hourly, daily and weekend patterns
   - Analyse bicycle availability by hour of the day.
   - Compare weekday and weekend patterns.
   - Identify peak and low-availability periods.
 ###### C. Frequent near-empty conditions
   - Identify stations that frequently have 2 or fewer bicycles.
   - Calculate the frequency and percentage of near-empty observations.
   - Rank stations based on their near-empty frequency.
###### D. Weather and bicycle availability
   - Explore relationships between temperature and bicycle availability.
   - Analyse the impact of rainfall and wind speed.
   - Compare bicycle availability under different weather conditions.
   - Investigate whether weather patterns are associated with changes in bicycle availability.
   
##### 4. Prepare EDA Outputs

   - Generate descriptive statistics and visualisations.
   - Create station-level comparison charts.
   - Produce hourly and weekday/weekend charts.
   - Visualise near-empty station frequency.
   - Present weather-related analysis.
   - Document the key findings and observations

### #2.YouTube Trending Project: Collect, Study, Show
1. Which kinds of videos (music, gaming and so on) are popular in Ireland compared with the UK and the US?
  2. How long does a video stay on the chart in each country? (Ireland's videos seem to stay much longer.)
  3. How many videos are popular in all three countries at once?
  4. Do short videos, big channels or upload time help a video stay on the chart longer?

To make an accurate prediction we would need 500-1000 data points. Youtube is not giving historical data Collecting data weekly for 4-8 weeks then predicting the increase in views for next week. Due to the time frame this is not possible .I collected real data and stored this in the data/raw folder.


### #1.Cybersecurity Vulnerability Intelligence and Analysis System
 -Collect cybersecurity vulnerability data using the NVD API.
 Data Source
1.CISA Known Exploited Vulnerabilities (KEV): Provides information about vulnerabilities known to have been exploited in the wild.
https://www.cisa.gov/known-exploited-vulnerabilities-catalog
2.FIRST Exploit Prediction Scoring System (EPSS): Provides daily probability scores estimating the likelihood of vulnerability exploitation within the next 30 days.
https://www.first.org/epss/
National Vulnerability Database (NVD)
https://nvd.nist.gov/
