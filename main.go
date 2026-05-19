package main

import (
	"fmt"
	"os"

	"wiki-tools/internal/cmd"
)

func main() {
	if len(os.Args) < 2 {
		cmd.PrintUsage()
		os.Exit(0)
	}

	name := os.Args[1]

	switch name {
	case "-h", "--help":
		cmd.PrintUsage()
		os.Exit(0)
	case "-v", "--version":
		fmt.Printf("wiki-tools v%s\n", cmd.Version)
		os.Exit(0)
	}

	handler, ok := cmd.Commands[name]
	if !ok {
		fmt.Fprintf(os.Stderr, "❌ 未知命令: %s\n\n", name)
		cmd.PrintUsage()
		os.Exit(1)
	}
	handler(os.Args[2:])
}
