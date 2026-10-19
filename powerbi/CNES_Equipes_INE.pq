// Tabela "CNES - Equipes INE" lendo do GitHub (foto atual + anterior)
let
    Base = CNES_URL_BASE,   // parâmetro: https://raw.githubusercontent.com/fabiodiehl0402/aps-cnes-ine/main/dados/
    Ler = (pasta as text, sufixo as text) as table =>
        let
            Lista = Lines.FromBinary(Web.Contents(Base, [RelativePath = pasta & "/_arquivos.txt"]), null, null, 65001),
            Arqs = List.Select(Lista, each Text.EndsWith(_, sufixo)),
            Tabs = List.Transform(Arqs, each Table.PromoteHeaders(Csv.Document(Binary.Decompress(Web.Contents(Base, [RelativePath = pasta & "/" & _]), Compression.GZip), [Delimiter = ";", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]), [PromoteAllScalars = true]))
        in
            if List.IsEmpty(Tabs) then #table({}, {}) else Table.Combine(Tabs),
    Atual = Ler("atual", "_equipes.csv.gz"),
    Anterior = try Ler("anterior", "_equipes.csv.gz") otherwise #table({}, {}),
    C = Table.Distinct(Table.Combine({Atual, Anterior}), {"data_ref", "ine"}),
    Ty = Table.TransformColumnTypes(C, {{"data_ref", type date}, {"ibge", Int64.Type}, {"cnes", Int64.Type}, {"estabelecimento", type text}, {"ine", Int64.Type}, {"tipo", type text}, {"tipo_cnes", type text}, {"nome_equipe", type text}, {"area", type text}, {"dt_ativacao", type text}, {"dt_desativacao", type text}, {"n_medico", Int64.Type}, {"n_enfermeiro", Int64.Type}, {"n_tec_enf", Int64.Type}, {"n_acs", Int64.Type}, {"n_dentista", Int64.Type}, {"n_asb_tsb", Int64.Type}, {"n_outros", Int64.Type}, {"n_total", Int64.Type}, {"faltando", type text}, {"situacao", type text}, {"ult_entrada", type text}, {"entradas_120d", Int64.Type}}, "en-US")
in
    Ty
