#!/bin/bash

echo "================================"
echo "Testing Git Bash Script"
echo "================================"
echo ""

# Print current directory
echo "Current directory: $(pwd)"
echo ""

# Print date and time
echo "Current date: $(date)"
echo ""

# List files
echo "Files in current directory:"
ls -la
echo ""

# Check Node.js version
echo "Node.js version:"
node --version
echo ""

# Check npm version
echo "npm version:"
npm --version
echo ""

# Simple variable
NAME="John"
echo "Hello, $NAME!"
echo ""

# Simple loop
echo "Counting to 5:"
for i in 1 2 3 4 5
do
   echo "Count: $i"
done
echo ""

echo "Script completed successfully!"