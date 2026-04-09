#!/bin/bash
# Quick deploy script for Radar.Toys frontend updates

set -e

# Load GitHub token from .env
if [ -f .env ]; then
    export $(grep GITHUB_TOKEN .env | xargs)
else
    echo "❌ Error: .env file not found"
    exit 1
fi

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ Error: GITHUB_TOKEN not found in .env"
    exit 1
fi

echo "📦 Checking for changes..."
if [ -z "$(git status --porcelain)" ]; then
    echo "✅ No changes to deploy"
    exit 0
fi

echo "📝 Committing changes..."
git add .
git commit -m "Frontend updates - $(date '+%Y-%m-%d %H:%M')"

echo "🚀 Pushing to GitHub..."
git push https://$GITHUB_TOKEN@github.com/Perna-ai/radar.toys.git main

echo "✅ Deploy complete! Vercel will auto-deploy in ~2 minutes"
echo "🌐 Check: https://radar-toys.vercel.app/"
