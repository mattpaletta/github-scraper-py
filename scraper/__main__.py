from bs4 import BeautifulSoup
import os
import sys
import requests
import github3
import getpass
import collections
import selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from configs import Parser

gh = None
p = Parser(argparse_file = "scraper/argparse.yml").get()

User = collections.namedtuple('User', 'name login github email job link bio')

chrome_options = Options()
chrome_options.add_argument("--user-data-dir=chrome-data")
def chromedriver_location():
    import subprocess
    proc = subprocess.Popen(["which", "chromedriver"], stdout=subprocess.PIPE)

    return proc.communicate()[0].decode().strip()

if chromedriver_location() == "":
    print("`chromedriver` not found.")
    print("Please run: ")
    print("\t brew cask install chromedriver")
    print("(on macOS)")
    print("Or: ")
    print("\t apt-get install chromedriver")
    print("(on ubuntu)")
    exit(1)

driver = webdriver.Chrome(chromedriver_location(), options=chrome_options)

def login_to_github():
    driver.get( "https://github.com/login" )
    driver.implicitly_wait(5)
    if driver.current_url != "https://github.com/":
        wait = input("Login to github, then hit enter")

def get_user_link(user):
    return "https://github.com/" + str(user)

def get_user_profile_logged_in(user):
    driver.get( get_user_link(user) )
    driver.implicitly_wait(5)
    html = driver.page_source
    return html

def get_user_profile_raw(user):
    r = requests.get( get_user_link(user) )
    return r.content

def get_user_profile(html):
    soup = BeautifulSoup(html, 'html.parser')
    return soup

def get_github():
    global gh
    global p
    if gh is None:
        if p.get("user") is None:
            user_login = input("User: ")
        else:
            user_login = p.get("user")
        user_password = getpass.getpass()
        gh = github3.login(user_login, password = user_password)
        assert(gh.ratelimit_remaining > 0)
    return gh

def get_repository(owner, repository_name):
    return get_github().repository(owner, repository_name)

def get_forks(owner, repository_name):
    global p
    return get_repository(owner, repository_name).forks(number=p.get("limit"))

def get_stars(owner, repository_name):
    global p
    return get_repository(owner, repository_name).stargazers(p.get("limit"))

def get_full_name(soup):
    full_name = soup.find("span", {"class": "vcard-fullname"})
    if full_name is None:
        return None
    if len(full_name.contents) > 0:
        return full_name.contents[0]
    return None

def get_email(soup):
    email = soup.find("a", {"class": "u-email"})
    if email is None:
        return None
    return email.contents[0]

def get_job(soup):
    job = soup.find("span", {"class": "p-org"})
    if job is None:
        return None
    if type(job) is list:
        if len(job.contents) > 0:
            job_div = job.contents[0]
            if len(job_div.contents) > 0:
                return job_div.contents[0]
    else:
        return job.contents[0]
    return None

def get_link(soup):
    links = soup.findAll("li", {"class": "vcard-detail"})
    for link in links:
        a = link.find("a", {'rel': 'nofollow me'})
        if a is not None:
            return a.contents[0]
    return None

def get_bio(soup):
    bio = soup.find("div", {"class": "user-profile-bio"})
    if bio is not None:
        if len(bio.contents) > 0:
            bio_content = bio.contents
            if len(bio_content) > 0:
                return bio_content[0].contents[0]
    return None

def extract_profile(soup):
    full_name = get_full_name( soup )
    email = get_email( soup )
    job = get_job( soup )
    link = get_link( soup )
    bio = get_bio( soup )
    return (full_name, email, job, link, bio)

def read_repositories(repo_file: str):
    if os.path.exists(repo_file):
        with open(repo_file, "r") as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith("#"):
                    continue
                spl = line.split("/")
                if len(spl) == 2:
                    yield spl[0].strip(), spl[1].strip()
                else:
                    print("Repo invalid formatting: (owner/repository) [{0}]".format(line))

def get_users(owner, repository_name):
    stars = get_stars(owner, repository_name)
    for star in stars:
        yield star.login

    forks = get_forks(owner, repository_name)
    for fork in forks:
        yield fork.owner.login

def get_repo_list_users(repo_file):
    for owner, repository_name in read_repositories(repo_file):
        print("Reading repo: {0} / {1}".format(owner, repository_name))
        for user in get_users(owner, repository_name):
            yield user
        print(" ")

def read_existing_users(filename):
    if os.path.exists(filename):
        return pd.read_csv(filename)
    else:
        return pd.DataFrame([], columns = ["login"])

def user_exists(df, value):
    found = df[df['login'].str.contains(value)]
    return found.count() > 0


def has_field(value):
    return value is not None or (type(value) is str and value != "")

def process_users(repo_file):
    print("Reading old users")
    old_df = read_existing_users("output.csv")
    print("Found: {0} old users".format(old_df.count()))
    processed_users = old_df["login"].values.tolist()

    for login in get_repo_list_users(repo_file):
        if str(login) not in processed_users:
            print(".", end="")
            sys.stdout.flush()
            html = get_user_profile_logged_in(user = login)
            full_name, email, job, link, bio = extract_profile( get_user_profile( html) )
            processed_users.append(login)
            if has_field(email) or has_field(link):
                yield User(name = full_name,
                           login = login,
                           github = get_user_link(login),
                           email = email,
                           job = job,
                           link = link,
                           bio = bio)

def main():
    global p
    login_to_github()
    df = pd.DataFrame(data = process_users(p.get("repo")))
    old_df = read_existing_users(p.get("output"))
    pd.concat([df, old_df], ignore_index=True, sort=True).to_csv(p.get("output"), index=False, columns=['name', 'login', 'github', 'email', "link", "job", "bio"])

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error)
    driver.quit()
