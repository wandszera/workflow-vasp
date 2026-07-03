#!/bin/bash

output_file="energias_totais.csv"

# Cabeçalho CSV
echo "diretorio,energia_eV" > "$output_file"

# Loop em todos os diretórios de nível superior
for dir in */; do
    dir=${dir%/}
    outcar="$dir/OUTCAR"
    energia="NaN"

    if [[ -f "$outcar" ]]; then
        if grep -q "reached required accuracy - stopping structural energy minimisation" "$outcar"; then
            # Renomeia se convergiu mas ainda não tiver _OK
            if [[ ! "$dir" =~ _OK$ ]]; then
                newdir="${dir}_OK"
                mv "$dir" "$newdir"
                echo "Renomeado: $dir → $newdir"
                dir="$newdir"
                outcar="$dir/OUTCAR"
            fi

            energia=$(grep "free  energy   TOTEN" "$outcar" | tail -1 | awk '{print $5}')
        fi
    fi

    # Escreve CSV (sempre duas colunas, sem texto livre)
    echo "$dir,$energia" >> "$output_file"
done

echo "Processamento concluído. Arquivo gerado: $output_file"
