# dashboard-de-ativos
Dashboard de ativos – Sinalização de compras e vendas

Manual:

💡 Primeiro uso (setup inicial)

    Abrir a aplicação Streamlit
    
    Acesse o link da aplicação: https://proj-aplic-xp-dashboard-de-ativos.streamlit.app/
    
    Cadastrar seu primeiro ativo

No Sidebar → ⚙️ Gerenciar Ativos → Cadastrar Ação:

    Informe o Código do Ativo (ex: PETR4).
    
    O sistema adiciona .SA automaticamente.
    
    Informe o Preço Médio que você pagou pelo ativo.
    
    Informe o Preço Teto, que será usado como referência para alertas.
    
    Clique em Salvar Ação.

    O sistema valida se o ativo existe no Yahoo Finance e salva a ação.
    
    Pronto!

    A ação foi registrada e o sistema começará a monitorar o preço e alertas automaticamente.

💡 Usos seguintes

Adicionar novos ativos

    Repetir o processo em Cadastrar Ação para cada novo ativo.
    
    Atualizar preços ou teto de ativos existentes
    
        Sidebar → Editar Ação:
        
        Selecione o ativo.
        
        Atualize Preço Médio ou Preço Teto.
        
        Clique em Atualizar Ação.
    
    Remover ativos
    
        Sidebar → Excluir Ação:
        
        Selecione o ativo.
        
        Clique em Remover.
    
    O sistema funciona sozinho
    
    Ele vai buscar automaticamente o preço atualizado do ativo e avaliar se ele está abaixo, acima ou dentro do teto definido, mesmo que o usuário não veja gráficos ou dados complexos.
