#importando os módulos
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource, 
                       QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink,
                       QgsFeatureSink, QgsFeature, QgsGeometry, QgsVectorLayer, QgsField, QgsProject)

#definindo classe e inputs
class IdentificarMudancas(QgsProcessingAlgorithm):
    INPUT_LAYER_1 = 'INPUT_LAYER_1'
    INPUT_LAYER_2 = 'INPUT_LAYER_2'
    PONTOS_TRACKER = 'PONTOS_TRACKER'
    CHAVE_PRIMARIA = 'CHAVE_PRIMARIA'
    TOLERANCIA = 'TOLERANCIA'
    ATRIBUTOS_IGNORADOS = 'ATRIBUTOS_IGNORADOS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

    #usando initAlgorithm para iniciailizar todos os parâmtros  
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_LAYER_1,
                'Camada do dia 1',
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_LAYER_2,
                'Camada do dia 2',
                [QgsProcessing.TypeVectorAnyGeometry]
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.PONTOS_TRACKER,
                'Camada de pontos (tracker)',
                [QgsProcessing.TypeVectorPoint]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.CHAVE_PRIMARIA,
                'Atributo correspondente à chave primária',
                parentLayerParameterName=self.INPUT_LAYER_1,
                type=QgsProcessingParameterField.Any
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.TOLERANCIA,
                'Distância de tolerância (metros)',
                type=QgsProcessingParameterNumber.Double,
                defaultValue=2.0
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_LAYER,
                'Camada de mudanças'
            )
        )
    #início do processing principal
    def processAlgorithm(self, parameters, context, feedback):
        #camadas e parâmetros fornecidos pelo usuário
        camada_dia_1 = self.parameterAsSource(parameters, self.INPUT_LAYER_1, context)
        camada_dia_2 = self.parameterAsSource(parameters, self.INPUT_LAYER_2, context)
        camada_pontos = self.parameterAsSource(parameters, self.PONTOS_TRACKER, context)
        chave_primaria = self.parameterAsString(parameters, self.CHAVE_PRIMARIA, context)
        tolerancia = self.parameterAsDouble(parameters, self.TOLERANCIA, context)

        #lista com os atributos a serem ignorados
        atributos_ignorados = self.get_ignored_attributes(camada_dia_1)

        #lista com os atributos que devem ser comparados
        atributos_comparar = [field.name() for field in camada_dia_1.fields() if field.name() not in atributos_ignorados]

      #criamos a camada de saída 
        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            camada_dia_1.fields(),
            camada_dia_1.wkbType(),
            camada_dia_1.sourceCrs()
        )

        #identificamos mudanças entre as camadas
        self.identificar_mudancas(camada_dia_1, camada_dia_2, sink, atributos_comparar, chave_primaria, tolerancia, context, feedback)

        return {self.OUTPUT_LAYER: dest_id}

    #método para obter os atributos a serem ignorados, de forma que formem uma lista para o usuário selecionar
    def get_ignored_attributes(self, layer):
        dialog = AtributosDialog([field.name() for field in layer.fields()])
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_selected_atributos()
        else:
            return []

     #definindo a função que vai identificar as mudanças e classificar 
    def identificar_mudancas(self, camada_dia_1, camada_dia_2, sink, atributos_comparar, chave_primaria, tolerancia, context, feedback):
      #usamos a função wkbtype para conseguirmos colocar qualquer geometria na camada de entrada 
        geom_type = camada_dia_1.wkbType()
      #cria um dicionário com os IDs e as feições da camada do dia 2 para acesso rápido
        ids_dia_2 = {feature.attribute(chave_primaria): feature for feature in camada_dia_2.getFeatures()}

       #itera sobre as camadas do dia 1, obtem id e geometria do dia 1 e busca correspondente no dia 2
        for feature_dia_1 in camada_dia_1.getFeatures():
            if feedback.isCanceled():
                break
            id_dia_1 = feature_dia_1.attribute(chave_primaria)
            geom_dia_1 = feature_dia_1.geometry()
            
            feature_proxima = ids_dia_2.get(id_dia_1, None)

            if feature_proxima:
              #compara mudanças, olha se a geometria mudou
                mudancas = comparar_atributos(feature_dia_1, feature_proxima, atributos_comparar)
                if not geom_dia_1.equals(feature_proxima.geometry()):
                    mudancas.append("geometria")
                if mudancas:
                    tipo_mudanca = "Modificada"
                    nova_feature = QgsFeature()
                    nova_feature.setGeometry(geom_dia_1)
                    nova_feature.setAttributes([id_dia_1, tipo_mudanca, ", ".join(mudancas)])
                    sink.addFeature(nova_feature, QgsFeatureSink.FastInsert)
            else:
                tipo_mudanca = "Removida"
                nova_feature = QgsFeature()
                nova_feature.setGeometry(geom_dia_1)
                nova_feature.setAttributes([id_dia_1, tipo_mudanca, ""])
                sink.addFeature(nova_feature, QgsFeatureSink.FastInsert)
              
        #segue os mesmos passos comparando o dia 1 com o dia 2
        ids_dia_1 = {feature.attribute(chave_primaria) for feature in camada_dia_1.getFeatures()}

        for feature_dia_2 in camada_dia_2.getFeatures():
            if feedback.isCanceled():
                break
            id_dia_2 = feature_dia_2.attribute(chave_primaria)
            geom_dia_2 = feature_dia_2.geometry()

            if id_dia_2 not in ids_dia_1:
                tipo_mudanca = "Adicionada"
                nova_feature = QgsFeature()
                nova_feature.setGeometry(geom_dia_2)
                nova_feature.setAttributes([id_dia_2, tipo_mudanca, ""])
                sink.addFeature(nova_feature, QgsFeatureSink.FastInsert)
              
    #apenas define nome e nome a ser exibido
    def name(self):
        return 'identificar_mudancas'

    def displayName(self):
        return 'Identificar Mudanças'

    def group(self):
        return 'Exemplo de Algoritmo'

    def groupId(self):
        return 'exemplo_algoritmo'

    def createInstance(self):
        return IdentificarMudancas()
      
  #nosso código só rodou a caixa de atributos quando usamos essa checkbox, ela está deslocada, mas ainda se refere a caixa inicial
class AtributosDialog(QDialog):
    def __init__(self, atributos, parent=None):
        super(AtributosDialog, self).__init__(parent)
        self.setWindowTitle('Selecionar Atributos para Ignorar')
        self.layout = QVBoxLayout(self)
        self.checkboxes = []
        
        for atributo in atributos:
            checkbox = QCheckBox(atributo)
            self.layout.addWidget(checkbox)
            self.checkboxes.append(checkbox)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.layout.addWidget(self.buttons)
        
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def get_selected_atributos(self):
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]

#compara os atributos finais 
def comparar_atributos(feature1, feature2, atributos_comparar):
    mudancas = []
    for nome_campo in atributos_comparar:
        valor1 = feature1[nome_campo]
        valor2 = feature2[nome_campo]
        if valor1 != valor2:
            mudancas.append(nome_campo)
    return mudancas

#registrar o algoritmo no QGIS
def classFactory(iface):
    from qgis.core import QgsApplication
    QgsApplication.processingRegistry().addProvider(IdentificarMudancas())
    


#codigo anterior
'''from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QInputDialog, QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox
from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFeature, 
                       QgsGeometry, QgsPoint)

# Função para obter a lista de camadas carregadas no QGIS
def obter_lista_camadas():
    return [layer.name() for layer in QgsProject.instance().mapLayers().values()]

# Função para carregar camada a partir do nome selecionado
def carregar_camada(nome_camada):
    camada = QgsProject.instance().mapLayersByName(nome_camada)[0]
    if not camada.isValid():
        raise Exception(f"Falha ao carregar a camada {nome_camada}!")
    return camada

# Função para comparar atributos e identificar mudanças
def comparar_atributos(feature1, feature2, atributos_comparar):
    mudancas = []
    for nome_campo in atributos_comparar:
        valor1 = feature1[nome_campo]
        valor2 = feature2[nome_campo]
        if valor1 != valor2:
            mudancas.append(nome_campo)
    return mudancas

# Função para criar camada de mudanças
def criar_camada_mudancas(nome_camada, geom_type):
    camada = QgsVectorLayer(f"{geom_type}?crs=EPSG:4326", nome_camada, "memory")
    camada.startEditing()
    camada.addAttribute(QgsField("id", QVariant.String))
    camada.addAttribute(QgsField("tipo_mudanca", QVariant.String))
    camada.addAttribute(QgsField("atributos_modificados", QVariant.String))
    camada.updateFields()
    return camada

# Função para identificar mudanças entre duas camadas
def identificar_mudancas(camada_dia_1, camada_dia_2, nome_camada_mudancas, atributos_comparar, chave_primaria):
    geom_type = camada_dia_1.geometryType()
    geom_type_str = {0: "Point", 1: "LineString", 2: "Polygon"}.get(geom_type, "Unknown")
    camada_mudancas = criar_camada_mudancas(nome_camada_mudancas, geom_type_str)
    ids_dia_2 = {feature.attribute(chave_primaria): feature for feature in camada_dia_2.getFeatures()}

    for feature_dia_1 in camada_dia_1.getFeatures():
        id_dia_1 = feature_dia_1.attribute(chave_primaria)
        geom_dia_1 = feature_dia_1.geometry()
        
        feature_proxima = ids_dia_2.get(id_dia_1, None)

        if feature_proxima:
            mudancas = comparar_atributos(feature_dia_1, feature_proxima, atributos_comparar)
            if not geom_dia_1.equals(feature_proxima.geometry()):
                mudancas.append("geometria")
            if mudancas:
                tipo_mudanca = "Modificada"
                nova_feature = QgsFeature()
                nova_feature.setGeometry(geom_dia_1)
                nova_feature.setAttributes([id_dia_1, tipo_mudanca, ", ".join(mudancas)])
                camada_mudancas.addFeature(nova_feature)
        else:
            tipo_mudanca = "Removida"
            nova_feature = QgsFeature()
            nova_feature.setGeometry(geom_dia_1)
            nova_feature.setAttributes([id_dia_1, tipo_mudanca, ""])
            camada_mudancas.addFeature(nova_feature)

    ids_dia_1 = {feature.attribute(chave_primaria) for feature in camada_dia_1.getFeatures()}

    for feature_dia_2 in camada_dia_2.getFeatures():
        id_dia_2 = feature_dia_2.attribute(chave_primaria)
        geom_dia_2 = feature_dia_2.geometry()

        if id_dia_2 not in ids_dia_1:
            tipo_mudanca = "Adicionada"
            nova_feature = QgsFeature()
            nova_feature.setGeometry(geom_dia_2)
            nova_feature.setAttributes([id_dia_2, tipo_mudanca, ""])
            camada_mudancas.addFeature(nova_feature)

    # Remover feições com 'nao_modificado'
    camada_mudancas.startEditing()
    for feature in camada_mudancas.getFeatures():
        if feature['atributos_modificados'] == "nao_modificado":
            camada_mudancas.deleteFeature(feature.id())
    camada_mudancas.commitChanges()

    QgsProject.instance().addMapLayer(camada_mudancas)
    print(f"Camada de mudanças {nome_camada_mudancas} adicionada ao projeto!")

# Diálogo personalizado para selecionar múltiplos atributos
class AtributosDialog(QDialog):
    def __init__(self, atributos, parent=None):
        super(AtributosDialog, self).__init__(parent)
        self.setWindowTitle('Selecionar Atributos para Ignorar')
        self.layout = QVBoxLayout(self)
        self.checkboxes = []
        
        for atributo in atributos:
            checkbox = QCheckBox(atributo)
            self.layout.addWidget(checkbox)
            self.checkboxes.append(checkbox)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.layout.addWidget(self.buttons)
        
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

    def get_selected_atributos(self):
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]

# Função para solicitar entrada do usuário
def solicitar_entrada():
    lista_camadas = obter_lista_camadas()
    
    nome_camada_pontos, _ = QInputDialog.getItem(None, "Entrada de Dados", "Nome da camada de pontos:", lista_camadas, 0, False)
    nome_camada_dia_1, _ = QInputDialog.getItem(None, "Entrada de Dados", "Nome da camada do dia 1:", lista_camadas, 0, False)
    
    # Carregar a camada do dia 1 antes de solicitar atributos
    camada_dia_1 = carregar_camada(nome_camada_dia_1)
    atributos_disponiveis = [field.name() for field in camada_dia_1.fields()]
    
    nome_camada_dia_2, _ = QInputDialog.getItem(None, "Entrada de Dados", "Nome da camada do dia 2:", lista_camadas, 0, False)
    distancia_tolerancia, _ = QInputDialog.getDouble(None, "Entrada de Dados", "Distância de tolerância (metros):", decimals=2)
    chave_primaria, _ = QInputDialog.getItem(None, "Entrada de Dados", "Atributo correspondente à chave primária:", atributos_disponiveis, 0, False)

    # Diálogo personalizado para selecionar múltiplos atributos
    dialog = AtributosDialog(atributos_disponiveis)
    if dialog.exec_() == QDialog.Accepted:
        atributos_ignorados = dialog.get_selected_atributos()
    else:
        atributos_ignorados = []
    
    return nome_camada_pontos, nome_camada_dia_1, nome_camada_dia_2, distancia_tolerancia, chave_primaria, atributos_ignorados

# Solicitar entrada do usuário
(nome_camada_pontos, nome_camada_dia_1, nome_camada_dia_2, distancia_tolerancia, chave_primaria, atributos_ignorados) = solicitar_entrada()

# Carregar as camadas a partir das seleções do usuário
camada_pontos = carregar_camada(nome_camada_pontos)
camada_dia_1 = carregar_camada(nome_camada_dia_1)
camada_dia_2 = carregar_camada(nome_camada_dia_2)

# Filtrar os atributos a serem comparados
atributos_comparar = [field.name() for field in camada_dia_1.fields() if field.name() not in atributos_ignorados]

# Identificar mudanças e criar a camada de mudanças
identificar_mudancas(camada_dia_1, camada_dia_2, "mudancas_detectadas", atributos_comparar, chave_primaria)

# Criar a camada de linha baseada na camada de pontos "tracker"
nome_camada_trajeto_gps = "trajetoria_do_gps"

# Criar uma nova camada de linha
camada_trajeto_gps = QgsVectorLayer("LineString?crs=EPSG:4326", nome_camada_trajeto_gps, "memory")
camada_trajeto_gps.startEditing()

# Adicionar um campo para o ID do ponto
field_id = QgsField(chave_primaria, QVariant.String)
camada_trajeto_gps.addAttribute(field_id)
camada_trajeto_gps.updateFields()

# Obter os pontos da camada "tracker"
pontos_tracker = []
atributos_tracker = []

# Coletar os pontos e seus atributos
for feature in camada_pontos.getFeatures():
    ponto = feature.geometry().asPoint()
    creation_time = feature.attribute("creation_time")
    id_ponto = feature.attribute(chave_primaria)
    pontos_tracker.append((ponto, creation_time, id_ponto))
    atributos_tracker.append(id_ponto)

# Ordenar os pontos com base no creation_time
pontos_tracker.sort(key=lambda x: x[1])

# Adicionar linhas entre pontos em ordem crescente de creation_time
for i in range(len(pontos_tracker) - 1):
    ponto_atual, _, id_ponto_atual = pontos_tracker[i]
    prox_ponto, _, id_prox_ponto = pontos_tracker[i + 1]
    
    ponto_atual_qgs = QgsPoint(ponto_atual.x(), ponto_atual.y())
    prox_ponto_qgs = QgsPoint(prox_ponto.x(), prox_ponto.y())
    
    linha_trajeto = QgsGeometry.fromPolyline([ponto_atual_qgs, prox_ponto_qgs])
    
    feature_trajeto = QgsFeature()
    feature_trajeto.setGeometry(linha_trajeto)
    feature_trajeto.setAttributes([id_ponto_atual])
    
    camada_trajeto_gps.addFeature(feature_trajeto)

camada_trajeto_gps.commitChanges()

# Adicionar a nova camada de linha ao projeto
QgsProject.instance().addMapLayer(camada_trajeto_gps)
print("Nova camada de linha adicionada ao projeto!")

# Comparar a camada trajeto_gps com a camada mudancas_detectadas e criar camada mudancas_final
def comparar_camadas_final(camada1, camada2, chave_primaria, nome_camada_final, tolerancia):
    geom_type = camada1.geometryType()
    geom_type_str = {0: "Point", 1: "LineString", 2: "Polygon"}.get(geom_type, "Unknown")
    camada_final = criar_camada_mudancas(nome_camada_final, geom_type_str)
    
    ids_camada2 = {feature.attribute(chave_primaria): feature for feature in camada2.getFeatures()}
    ids_camada1 = {feature.attribute(chave_primaria): feature for feature in camada1.getFeatures()}

    # Buffer ao redor da camada trajeto_gps
    for feature_camada1 in camada1.getFeatures():
        buffer_geom = feature_camada1.geometry().buffer(tolerancia, 5)
        id_camada1 = feature_camada1.attribute(chave_primaria)
        
        # Identificar adições e modificações
        for id_camada2, feature_camada2 in ids_camada2.items():
            if buffer_geom.intersects(feature_camada2.geometry()):
                if id_camada2 not in ids_camada1:
                    tipo_mudanca = "Adicionada"
                    nova_feature = QgsFeature()
                    nova_feature.setGeometry(feature_camada2.geometry())
                    nova_feature.setAttributes([id_camada2, tipo_mudanca, ""])
                    camada_final.addFeature(nova_feature)
                else:
                    mudancas = comparar_atributos(feature_camada1, feature_camada2, [chave_primaria])
                    if not feature_camada1.geometry().equals(feature_camada2.geometry()):
                        mudancas.append("geometria")
                    if mudancas:
                        tipo_mudanca = "Modificada"
                        nova_feature = QgsFeature()
                        nova_feature.setGeometry(feature_camada1.geometry())
                        nova_feature.setAttributes([id_camada1, tipo_mudanca, ", ".join(mudancas)])
                        camada_final.addFeature(nova_feature)

    # Identificar remoções
    for id_camada1, feature_camada1 in ids_camada1.items():
        if id_camada1 not in ids_camada2:
            tipo_mudanca = "Removida"
            nova_feature = QgsFeature()
            nova_feature.setGeometry(feature_camada1.geometry())
            nova_feature.setAttributes([id_camada1, tipo_mudanca, ""])
            camada_final.addFeature(nova_feature)

    camada_final.commitChanges()
    QgsProject.instance().addMapLayer(camada_final)
    print(f"Camada de mudanças {nome_camada_final} adicionada ao projeto!")

# Comparar as camadas trajeto_gps e mudancas_detectadas e criar camada mudancas_final
trajetoria_gps = QgsProject.instance().mapLayersByName(nome_camada_trajeto_gps)[0]
mudancas_detectadas = QgsProject.instance().mapLayersByName("mudancas_detectadas")[0]
comparar_camadas_final(trajetoria_gps, mudancas_detectadas, chave_primaria, "mudancas_final", distancia_tolerancia)'''
