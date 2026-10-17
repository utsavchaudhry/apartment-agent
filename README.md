# Apartment Agent

Scans Kleinanzeigen, WG-Gesucht and ImmoScout24 around the clock, scores every new rental ad against your criteria, pushes good matches to your phone, and drafts the enquiry for you. Preferences and results live in a web dashboard.

## Run it

Needs Docker and git. Install them once:

```bash
# Windows (PowerShell), then start Docker Desktop
winget install -e --id Docker.DockerDesktop
winget install -e --id Git.Git

# macOS (Homebrew), then start Docker Desktop
brew install --cask docker
brew install git

# Ubuntu / Debian / Raspberry Pi OS
sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
```

On Windows and macOS, turn on **Docker Desktop → Settings → General → Start Docker Desktop when you sign in**, so the agent comes back after a restart. It only scans while the computer is awake, so an always-on machine (a Raspberry Pi, a home server) catches flats fastest.

Start the agent (it keeps running in the background and comes back after a reboot):

```bash
git clone https://github.com/utsavchaudhry/apartment-agent.git
cd apartment-agent
docker compose up -d --build
```

Open the dashboard at **http://localhost:8080** (or `http://<machine-ip>:8080` from another device), then:

1. **Settings** → set budget, move-in window, commute postcodes and your applicant details → **Save**.
2. Install the **ntfy** app on your phone, tap **+** and subscribe to the topic shown under **Settings → Phone notifications**, then press **Send test**.

## Optional

Password-protect the dashboard:

```bash
echo "DASHBOARD_PASSWORD=choose-something" > .env
docker compose up -d
```

Update to the latest version:

```bash
git pull
docker compose up -d --build
```

Logs:

```bash
docker compose logs -f
```
