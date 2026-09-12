package migrations

import (
	"embed"
	"sort"
)

//go:embed *.sql
var files embed.FS

type Migration struct{ Name, SQL string }

func All() []Migration {
	entries, err := files.ReadDir(".")
	if err != nil {
		panic(err)
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() {
			names = append(names, entry.Name())
		}
	}
	sort.Strings(names)
	result := make([]Migration, 0, len(names))
	for _, name := range names {
		sql, err := files.ReadFile(name)
		if err != nil {
			panic(err)
		}
		result = append(result, Migration{Name: name, SQL: string(sql)})
	}
	return result
}
