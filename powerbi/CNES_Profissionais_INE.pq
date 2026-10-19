// Tabela "CNES - Profissionais INE" lendo do GitHub (foto atual + anterior)
let
    Base = CNES_URL_BASE,   // parâmetro: https://raw.githubusercontent.com/fabiodiehl0402/aps-cnes-ine/main/dados/
    Ler = (pasta as text, sufixo as text) as table =>
        let
            Lista = Lines.FromBinary(Web.Contents(Base, [RelativePath = pasta & "/_arquivos.txt"]), null, null, 65001),
            Arqs = List.Select(Lista, each Text.EndsWith(_, sufixo)),
            Tabs = List.Transform(Arqs, each Table.PromoteHeaders(Csv.Document(Binary.Decompress(Web.Contents(Base, [RelativePath = pasta & "/" & _]), Compression.GZip), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]), [PromoteAllScalars = true]))
        in
            if List.IsEmpty(Tabs) then #table({}, {}) else Table.Combine(Tabs),
    Atual = Ler("atual", "_profissionais.csv.gz"),
    Anterior = try Ler("anterior", "_profissionais.csv.gz") otherwise #table({}, {}),
    C = Atual,
    Ty = Table.TransformColumnTypes(C, {{"data_ref", type date}, {"ibge", Int64.Type}, {"ine", Int64.Type}, {"cbo", type text}, {"ocupacao", type text}, {"categoria", type text}, {"nome", type text}, {"ch_semanal", Int64.Type}, {"entrada", type date}}, "en-US")
in
    Ty
