from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
    QgsProcessingOutputVectorLayer,
)
from qgis import processing
from PyQt5.QtCore import QVariant
import processing
class ValidateAndCorrectFeaturesAlgorithm(QgsProcessingAlgorithm):

    INPUT_LINE_LAYER = 'INPUT_LINE_LAYER'
    OUTPUT_POINT_LAYER = 'OUTPUT_POINT_LAYER'
    CLASSIFY_FEATURES = 'CLASSIFY_FEATURES'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_LINE_LAYER,
                'Input Line Layer',
                [QgsProcessing.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POINT_LAYER,
                'Output Point Layer'
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CLASSIFY_FEATURES,
                'Classify Features',
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # Obter os parâmetros
        input_line_layer = self.parameterAsVectorLayer(parameters, self.INPUT_LINE_LAYER, context)
        output_point_layer = self.parameterAsSink(parameters, self.OUTPUT_POINT_LAYER, context, input_line_layer.fields(), QgsWkbTypes.Point, input_line_layer.crs())
        classify_features = self.parameterAsBool(parameters, self.CLASSIFY_FEATURES, context)

        # Lista para armazenar as feições inválidas
        invalid_features = []

        nr_pistas_idx = input_line_layer.fields().indexOf("nr_pistas")
        nr_faixas_idx = input_line_layer.fields().indexOf("nr_faixas")

        # Verificar se os campos "nr_pistas" e "nr_faixas" existem
        if nr_pistas_idx == -1 or nr_faixas_idx == -1:
            raise QgsProcessingException(f"Os campos 'nr_pistas' ou 'nr_faixas' não foram encontrados na camada '{input_line_layer.name()}'.")
        
        # Verificar e corrigir feições inválidas
        total_count = input_line_layer.featureCount()
        step = 10  # Processar em lotes de 10 feições
        current_count = 0

        for feature in input_line_layer.getFeatures():
            nr_pistas_value = feature["nr_pistas"]
            nr_faixas_value = feature["nr_faixas"]

            # Converter valores para inteiros se possível
            try:
                nr_pistas_value = int(nr_pistas_value)
            except (TypeError, ValueError):
                nr_pistas_value = 1  # Valor padrão se a conversão falhar

            try:
                nr_faixas_value = int(nr_faixas_value)
            except (TypeError, ValueError):
                nr_faixas_value = 1  # Valor padrão se a conversão falhar

            # Garantir que os valores sejam no mínimo 1
            if nr_pistas_value < 1:
                nr_pistas_value = 1
            if nr_faixas_value < 1:
                nr_faixas_value = 1

            # Verificar se nr_pistas é maior que nr_faixas ou se algum dos valores é menor que 1
            if nr_pistas_value > nr_faixas_value or nr_pistas_value < 1 or nr_faixas_value < 1:
                invalid_features.append(feature)

            # Criar feições na camada de ponto se necessário
            if classify_features:
                point_feature = QgsFeature()
                point_geometry = QgsGeometry.fromPointXY(feature.geometry().pointOnSurface())
                point_feature.setGeometry(point_geometry)
                point_feature.setAttributes(feature.attributes())
                output_point_layer.addFeature(point_feature, QgsFeatureSink.FastInsert)

            # Atualizar o progresso a cada lote processado
            current_count += 1
            if current_count % step == 0:
                feedback.setProgress(int(current_count / total_count * 100))

        # Transformar a camada de linha em pontos
        self.create_point_layer_from_line_layer(input_line_layer, output_point_layer)

        # Validar os pontos e plotar erros
        self.validate_points()

        # Retorna resultados
        return {self.OUTPUT_POINT_LAYER: output_point_layer}

    def create_point_layer_from_line_layer(self, line_layer, output_point_layer):
        # Cria uma nova camada de ponto
        point_layer = QgsVectorLayer('Point?crs=' + line_layer.crs().authid(), output_point_layer.name(), 'memory')
        point_layer_data = point_layer.dataProvider()

        # Copia todos os campos da camada de linha para a camada de ponto
        point_layer_data.addAttributes(line_layer.fields().toList())
        point_layer.updateFields()

        point_layer.startEditing()

        # Percorre todos os recursos na camada de linha
        for feature in line_layer.getFeatures():
            geometry = feature.geometry()
            if geometry is None:
                continue

            # Obtém os vértices da linha
            for vertex in geometry.vertices():
                point_feature = QgsFeature(point_layer.fields())
                point_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(vertex.x(), vertex.y())))
                point_feature.setAttributes(feature.attributes())
                point_layer.addFeature(point_feature)

        point_layer.commitChanges()

        # Adiciona a nova camada de ponto ao projeto QGIS
        QgsProject.instance().addMapLayer(point_layer)
        print(f"Camada de ponto '{output_point_layer.name()}' criada a partir da camada de linha '{line_layer.name()}'.")

    def validate_points(self):
        # Obter as camadas
        infra_elemento_viario_p = QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_elemento_viario_p")[0]
        infra_via_deslocamento_p = QgsProject.instance().mapLayersByName("infra_via_deslocamento_p")[0]

        # Filtrar pontos da camada infra_elemento_viario_p com tipo = 203
        infra_elemento_viario_p_203 = {feat.id(): feat for feat in infra_elemento_viario_p.getFeatures() if feat["tipo"] == 203}

        # Verificar pontos que satisfazem a regra 3
        common_ids = set(infra_elemento_viario_p_203.keys()) & {feat.id() for feat in infra_via_deslocamento_p.getFeatures()}

        # Verificar pontos que satisfazem a regra 4
        via_deslocamento_layer = QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_via_deslocamento_l")[0]
        vertices_via_deslocamento = {QgsPointXY(vertex.x(), vertex.y()) for feature in via_deslocamento_layer.getFeatures() for vertex in feature.geometry().vertices()}

        valid_points = {feat_id for feat_id in common_ids if QgsPointXY(infra_elemento_viario_p_203[feat_id].geometry().asPoint()) in vertices_via_deslocamento}

        # Verificar atributos nr_pistas, nr_faixas e situacao_fisica
        error_layer = QgsVectorLayer("Point?crs=" + infra_via_deslocamento_p.crs().authid(), "Erro_Regra_5", "memory")
        error_provider = error_layer.dataProvider()

        error_provider.addAttributes([QgsField("ID", QVariant.Int), QgsField("Classificacao", QVariant.String)])
        error_layer.updateFields()

        error_layer.startEditing()

        for feat_id in valid_points:
            feat_elemento = infra_elemento_viario_p_203[feat_id]
            feat_deslocamento = infra_via_deslocamento_p.getFeature(feat_id)

            if (feat_elemento["nr_pistas"] != feat_deslocamento["nr_pistas"] or
                    feat_elemento["nr_faixas"] != feat_deslocamento["nr_faixas"] or
                    feat_elemento["situacao_fisica"] != feat_deslocamento["situacao_fisica"]):
                error_feature = QgsFeature(error_layer.fields())
                error_feature.setGeometry(feat_elemento.geometry())
                error_feature["ID"] = feat_id
                error_feature["Classificacao"] = "Erro na Regra 5"
                error_layer.addFeature(error_feature)

        error_layer.commitChanges()
        QgsProject.instance().addMapLayer(error_layer)
        print("Camada de erro 'Erro_Regra_5' criada com sucesso.")

    def tr(self, string):
        return QgsProcessingAlgorithm.tr(string)

    def createInstance(self):
        return ValidateAndCorrectFeaturesAlgorithm()

    def name(self):
        return 'validate_and_correct_features_algorithm'

    def displayName(self):
        return self.tr('Validate and Correct Features Algorithm')

    def group(self):
        return self.tr('Projeto 4')

    def groupId(self):
        return 'projeto4'
    

    def shortHelpString(self):
        return self.tr("This algorithm validates and corrects features based on specified rules.")

# Registrar o algoritmo para que seja exibido na interface de processamento do QGIS
processing.registry().addAlgorithm(ValidateAndCorrectFeaturesAlgorithm())

'''
Código sem processing separado por regras:
Regra 1: Verificar os campos "nr_pistas" e "nr_faixas"
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsField, QgsWkbTypes
from PyQt5.QtCore import QVariant

def validate_and_correct_features(line_layer):
    # Lista para armazenar as feições inválidas
    invalid_features = []

    nr_pistas_idx = line_layer.fields().indexOf("nr_pistas")
    nr_faixas_idx = line_layer.fields().indexOf("nr_faixas")
    
    # Verificar se os campos "nr_pistas" e "nr_faixas" existem
    if nr_pistas_idx == -1 or nr_faixas_idx == -1:
        print(f"Os campos 'nr_pistas' ou 'nr_faixas' não foram encontrados na camada '{line_layer.name()}'.")
        return invalid_features
    
    for feature in line_layer.getFeatures():
        nr_pistas_value = feature["nr_pistas"]
        nr_faixas_value = feature["nr_faixas"]

        # Converter valores para inteiros se possível
        try:
            nr_pistas_value = int(nr_pistas_value)
        except (TypeError, ValueError):
            nr_pistas_value = 1  # Valor padrão se a conversão falhar

        try:
            nr_faixas_value = int(nr_faixas_value)
        except (TypeError, ValueError):
            nr_faixas_value = 1  # Valor padrão se a conversão falhar

        # Garantir que os valores sejam no mínimo 1
        if nr_pistas_value < 1:
            nr_pistas_value = 1
        if nr_faixas_value < 1:
            nr_faixas_value = 1

        # Verificar se nr_pistas é maior que nr_faixas ou se algum dos valores é menor que 1
        if nr_pistas_value > nr_faixas_value or nr_pistas_value < 1 or nr_faixas_value < 1:
            invalid_features.append(feature)

    return invalid_features

def create_point_layer_from_line_layer(line_layer, output_layer_name):
    # Cria uma nova camada de ponto
    point_layer = QgsVectorLayer('Point?crs=' + line_layer.crs().authid(), output_layer_name, 'memory')
    point_layer_data = point_layer.dataProvider()

    # Copia todos os campos da camada de linha para a camada de ponto
    point_layer_data.addAttributes(line_layer.fields().toList())
    point_layer.updateFields()

    point_layer.startEditing()

    # Percorre todos os recursos na camada de linha
    for feature in line_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None:
            continue

        # Obtém o ponto na superfície da linha
        point = geometry.pointOnSurface()

        point_feature = QgsFeature(point_layer.fields())
        point_feature.setGeometry(point)
        point_feature.setAttributes(feature.attributes())
        point_layer.addFeature(point_feature)

    point_layer.commitChanges()

    # Adiciona a nova camada de ponto ao projeto QGIS
    QgsProject.instance().addMapLayer(point_layer)
    print(f"Camada de ponto '{output_layer_name}' criada a partir da camada de linha '{line_layer.name()}'.")

def add_and_update_classification(point_layer):
    point_layer.startEditing()

    # Adicionar o campo "Classificacao" se não existir
    if "Classificacao" not in [field.name() for field in point_layer.fields()]:
        new_field = QgsField("Classificacao", QVariant.String)
        point_layer.dataProvider().addAttributes([new_field])
        point_layer.updateFields()

    classificacao_idx = point_layer.fields().indexOf("Classificacao")
    situacao_fisica_idx = point_layer.fields().indexOf("situacao_fisica")
    material_construcao_idx = point_layer.fields().indexOf("material_construcao")
    tipo_idx = point_layer.fields().indexOf("tipo")
    nr_pistas_idx = point_layer.fields().indexOf("nr_pistas")
    nr_faixas_idx = point_layer.fields().indexOf("nr_faixas")

    # Verificar se os campos necessários existem
    if situacao_fisica_idx == -1 or material_construcao_idx == -1 or tipo_idx == -1 or nr_pistas_idx == -1 or nr_faixas_idx == -1:
        print(f"Um dos campos necessários ('situacao_fisica', 'material_construcao', 'tipo', 'nr_pistas', 'nr_faixas') não foi encontrado na camada '{point_layer.name()}'.")
        point_layer.commitChanges()
        return

    # Percorre todos os recursos na camada de ponto
    for feature in point_layer.getFeatures():
        # Obter os valores dos atributos
        situacao_fisica_value = feature.attribute(situacao_fisica_idx)
        material_construcao_value = feature.attribute(material_construcao_idx)
        tipo_value = feature.attribute(tipo_idx)
        nr_pistas_value = feature.attribute(nr_pistas_idx)
        nr_faixas_value = feature.attribute(nr_faixas_idx)

        # Definir a classificação inicial baseada em "situacao_fisica"
        if situacao_fisica_value == 3:
            classificacao_value = "Correto"
        elif situacao_fisica_value == 1:
            classificacao_value = "Erro Abandono"
        else:
            classificacao_value = ""

        # Atualizar a classificação baseada em "material_construcao" e "tipo"
        if tipo_value == 401 and material_construcao_value == 3:
            classificacao_value = "Erro Material"

        # Verificar e atualizar a classificação com base em "nr_pistas" e "nr_faixas"
        try:
            nr_pistas_value = int(nr_pistas_value)
            nr_faixas_value = int(nr_faixas_value)
        except (TypeError, ValueError):
            nr_pistas_value = 1
            nr_faixas_value = 1

        if nr_pistas_value > nr_faixas_value or nr_pistas_value < 1 or nr_faixas_value < 1:
            classificacao_value = "Erro Material"

        # Definir o valor do atributo "Classificacao"
        feature.setAttribute(classificacao_idx, classificacao_value)
        point_layer.updateFeature(feature)

    point_layer.commitChanges()
    print(f"Campo 'Classificacao' adicionado e atualizado na camada '{point_layer.name()}'.")

# Obtenha as camadas de linha especificadas e crie camadas de ponto
line_layers = {
    "dados_projeto4_2024 — infra_via_deslocamento_l": "infra_via_deslocamento_p",
    "024 — elemnat_trecho_drenagem_ldados_projeto4_2": "elemnat_trecho_drenagem_p"
}

for line_layer_name, point_layer_name in line_layers.items():
    line_layer = QgsProject.instance().mapLayersByName(line_layer_name)
    if line_layer:
        create_point_layer_from_line_layer(line_layer[0], point_layer_name)
    else:
        print(f"Camada de linha '{line_layer_name}' não encontrada.")

# Adicionar e atualizar o campo "Classificacao" nas camadas de ponto especificadas
point_layers_to_verify = ["infra_via_deslocamento_p", "dados_projeto4_2024 — infra_elemento_viario_p"]

for point_layer_name in point_layers_to_verify:
    point_layer = QgsProject.instance().mapLayersByName(point_layer_name)
    if point_layer:
        add_and_update_classification(point_layer[0])
    else:
        print(f"Camada de ponto '{point_layer_name}' não encontrada.")

Regra 2: Verificar se os pontos da camada infra_elemento_viario_p com tipo = 203 estão presentes na camada infra_via_deslocamento_p

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource, 
                       QgsProcessingParameterFeatureSink, QgsFeature, QgsFields, QgsField,
                       QgsWkbTypes, QgsProcessing, QgsProject, QgsGeometry, QgsPointXY)
import processing

class ValidacaoElementosVarios(QgsProcessingAlgorithm):
    DRENAGEM = 'DRENAGEM'
    VIA_DESLOCAMENTO = 'VIA_DESLOCAMENTO'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.DRENAGEM,
                'Trecho de Drenagem',
                [QgsProcessing.TypeVectorLine]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.VIA_DESLOCAMENTO,
                'Via de Deslocamento',
                [QgsProcessing.TypeVectorLine]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                'Erros de Validação',
                QgsProcessing.TypeVectorPoint
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # Carregar camadas de entrada
        trecho_drenagem_layer = self.parameterAsSource(parameters, self.DRENAGEM, context)
        via_deslocamento_layer = self.parameterAsSource(parameters, self.VIA_DESLOCAMENTO, context)

        if not trecho_drenagem_layer or not via_deslocamento_layer:
            raise QgsProcessingException("Não foi possível carregar uma das camadas de entrada.")

        # Configurar a camada de saída
        fields = QgsFields()
        fields.append(QgsField('erro', QVariant.String))

        (sink, dest_id) = self.parameterAsSink(parameters, self.OUTPUT, context,
                                               fields, QgsWkbTypes.Point, trecho_drenagem_layer.sourceCrs())

        # Executar a função de interseção de linhas
        params = {
            'INPUT': parameters[self.DRENAGEM],
            'INTERSECT': parameters[self.VIA_DESLOCAMENTO],
            'INPUT_FIELDS': [],
            'INTERSECT_FIELDS': [],
            'INTERSECT_FIELDS_PREFIX': '',
            'OUTPUT': 'memory:'
        }

        intersection_result = processing.run("native:lineintersections", params, context=context, feedback=feedback)
        intersection_layer = intersection_result['OUTPUT']

        # Analisar as interseções para encontrar erros
        feature_map = {}
        for feature in intersection_layer.getFeatures():
            point = feature.geometry().asPoint()
            key = (point.x(), point.y())
            if key in feature_map:
                feature_map[key].append(feature)
            else:
                feature_map[key] = [feature]
        
        # Adicionar erros de validação à camada de saída
        for key, features in feature_map.items():
            if len(features) > 1:
                for feature in features:
                    error_feature = QgsFeature(fields)
                    error_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(key[0], key[1])))
                    error_feature.setAttributes(["Interseção múltipla"])
                    sink.addFeature(error_feature, QgsFeatureSink.FastInsert)

        return {self.OUTPUT: dest_id}

    def name(self):
        return "validacao_elementos_varios"

    def displayName(self):
        return "Validação de Elementos Viários"

    def group(self):
        return "Meu Grupo de Processamentos"

    def groupId(self):
        return "meu_grupo_de_processamentos"

    def createInstance(self):
        return ValidacaoElementosVarios()

# Registra o algoritmo na interface de processamento do QGIS
if __name__ == '__main__':
    from qgis import processing
    from qgis.core import QgsApplication
    QgsApplication.setPrefixPath(r'C:\PROGRA~1/QGIS33~1.0/apps/qgis', True)
    QgsApplication.initQgis()
    QgsApplication.processingRegistry().addAlgorithm(ValidacaoElementosVarios())

    # Executar o script
    params = {
        'DRENAGEM': 'caminho_para_sua_camada_de_drenagem',
        'VIA_DESLOCAMENTO': 'caminho_para_sua_camada_de_via_deslocamento',
        'OUTPUT': 'memory:'
    }

    processing.run("validacao_elementos_varios", params)

    QgsApplication.exitQgis()


Regra 3: Verificar se os pontos da camada infra_elemento_viario_p com tipo = 203 estão presentes na camada infra_via_deslocamento_p
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsWkbTypes, NULL
from PyQt5.QtCore import QVariant

def create_point_layer_from_line_layer(line_layer, output_layer_name):
    # Cria uma nova camada de ponto
    point_layer = QgsVectorLayer('Point?crs=' + line_layer.crs().authid(), output_layer_name, 'memory')
    point_layer_data = point_layer.dataProvider()

    # Copia todos os campos da camada de linha para a camada de ponto
    point_layer_data.addAttributes(line_layer.fields().toList())
    point_layer.updateFields()

    point_layer.startEditing()

    # Percorre todos os recursos na camada de linha
    for feature in line_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None:
            continue

        # Obtém o ponto na superfície da linha
        point = geometry.pointOnSurface()

        point_feature = QgsFeature(point_layer.fields())
        point_feature.setGeometry(point)
        point_feature.setAttributes(feature.attributes())
        point_layer.addFeature(point_feature)

    point_layer.commitChanges()

    # Adiciona a nova camada de ponto ao projeto QGIS
    QgsProject.instance().addMapLayer(point_layer)
    print(f"Camada de ponto '{output_layer_name}' criada a partir da camada de linha '{line_layer.name()}'.")

# Função para verificar e classificar pontos
def verify_and_classify_points():
    # Obter as camadas de ponto
    layers = {
        "infra_elemento_viario_p": QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_elemento_viario_p")[0],
        "infra_via_deslocamento_p": QgsProject.instance().mapLayersByName("infra_via_deslocamento_p")[0],
        "elemnat_trecho_drenagem_p": QgsProject.instance().mapLayersByName("elemnat_trecho_drenagem_p")[0]
    }

    # Coletar IDs de pontos em cada camada
    ids_in_layers = {name: set(feature.id() for feature in layer.getFeatures()) for name, layer in layers.items()}

    # Identificar pontos comuns às três camadas
    common_ids = ids_in_layers["infra_elemento_viario_p"] & ids_in_layers["infra_via_deslocamento_p"] & ids_in_layers["elemnat_trecho_drenagem_p"]

    # Criar uma nova camada de pontos para erros
    error_layer = QgsVectorLayer('Point?crs=' + layers["infra_elemento_viario_p"].crs().authid(), "Erro_Regra_3", "memory")
    error_layer_data = error_layer.dataProvider()
    error_layer_data.addAttributes([QgsField("ID", QVariant.Int), QgsField("Classificacao", QVariant.String)])
    error_layer.updateFields()

    error_layer.startEditing()

    # Verificar os pontos comuns e classificar
    for feature in layers["infra_elemento_viario_p"].getFeatures():
        if feature.id() in common_ids:
            tipo_value = feature["tipo"]
            if tipo_value not in {501, 203, 401}:
                error_feature = QgsFeature(error_layer.fields())
                error_feature.setGeometry(feature.geometry())
                error_feature["ID"] = feature.id()
                error_feature["Classificacao"] = "Erro Regra 3"
                error_layer.addFeature(error_feature)

    error_layer.commitChanges()

    # Adicionar a nova camada de erro ao projeto QGIS
    QgsProject.instance().addMapLayer(error_layer)
    print("Camada de erro 'Erro_Regra_3' criada com sucesso.")

# Obtenha as camadas de linha especificadas e crie camadas de ponto com o mesmo nome
line_layers = {
    "dados_projeto4_2024 — infra_via_deslocamento_l": "infra_via_deslocamento_p",
    "dados_projeto4_2024 — elemnat_trecho_drenagem_l": "elemnat_trecho_drenagem_p"
}

for line_layer_name, point_layer_name in line_layers.items():
    line_layer = QgsProject.instance().mapLayersByName(line_layer_name)
    if line_layer:
        create_point_layer_from_line_layer(line_layer[0], point_layer_name)
    else:
        print(f"Camada de linha '{line_layer_name}' não encontrada.")

# Verificar e classificar pontos
verify_and_classify_points()

Regra 4:
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsWkbTypes, NULL
from PyQt5.QtCore import QVariant

def create_point_layer_from_line_layer(line_layer, output_layer_name):
    # Cria uma nova camada de ponto
    point_layer = QgsVectorLayer('Point?crs=' + line_layer.crs().authid(), output_layer_name, 'memory')
    point_layer_data = point_layer.dataProvider()

    # Copia todos os campos da camada de linha para a camada de ponto
    point_layer_data.addAttributes(line_layer.fields().toList())
    point_layer.updateFields()

    point_layer.startEditing()

    # Percorre todos os recursos na camada de linha
    for feature in line_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None:
            continue

        # Obtém o ponto na superfície da linha
        point = geometry.pointOnSurface()

        point_feature = QgsFeature(point_layer.fields())
        point_feature.setGeometry(point)
        point_feature.setAttributes(feature.attributes())
        point_layer.addFeature(point_feature)

    point_layer.commitChanges()

    # Adiciona a nova camada de ponto ao projeto QGIS
    QgsProject.instance().addMapLayer(point_layer)
    print(f"Camada de ponto '{output_layer_name}' criada a partir da camada de linha '{line_layer.name()}'.")

def check_and_plot_errors():
    # Obter as camadas de ponto
    infra_elemento_viario_p = QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_elemento_viario_p")[0]
    infra_via_deslocamento_p = QgsProject.instance().mapLayersByName("infra_via_deslocamento_p")[0]
    elemnat_trecho_drenagem_p = QgsProject.instance().mapLayersByName("elemnat_trecho_drenagem_p")[0]

    # Coletar IDs de pontos em cada camada
    infra_elemento_viario_ids = set(feature.id() for feature in infra_elemento_viario_p.getFeatures())
    infra_via_deslocamento_ids = set(feature.id() for feature in infra_via_deslocamento_p.getFeatures())
    elemnat_trecho_drenagem_ids = set(feature.id() for feature in elemnat_trecho_drenagem_p.getFeatures())

    # Criar uma nova camada de pontos para erros
    error_layer = QgsVectorLayer('Point?crs=' + infra_elemento_viario_p.crs().authid(), "Erro_Regra_4", "memory")
    error_layer_data = error_layer.dataProvider()
    error_layer_data.addAttributes([QgsField("ID", QVariant.Int), QgsField("Classificacao", QVariant.String)])
    error_layer.updateFields()

    error_layer.startEditing()

    # Verificar os pontos e aplicar regras
    for feature in infra_elemento_viario_p.getFeatures():
        tipo_value = feature["tipo"]
        if tipo_value in {501, 203, 401}:
            if feature.id() in infra_via_deslocamento_ids:
                infra_via_deslocamento_feature = infra_via_deslocamento_p.getFeature(feature.id())
                if infra_via_deslocamento_feature["tipo"] == 2:
                    if feature.id() not in elemnat_trecho_drenagem_ids:
                        error_feature = QgsFeature(error_layer.fields())
                        error_feature.setGeometry(feature.geometry())
                        error_feature["ID"] = feature.id()
                        error_feature["Classificacao"] = "Erro da Regra 4"
                        error_layer.addFeature(error_feature)

    error_layer.commitChanges()

    # Adicionar a nova camada de erro ao projeto QGIS
    QgsProject.instance().addMapLayer(error_layer)
    print("Camada de erro 'Erro_Regra_4' criada com sucesso.")

# Obtenha as camadas de linha especificadas e crie camadas de ponto com o mesmo nome
line_layers = {
    "dados_projeto4_2024 — infra_via_deslocamento_l": "infra_via_deslocamento_p",
    "dados_projeto4_2024 — elemnat_trecho_drenagem_l": "elemnat_trecho_drenagem_p"
}

for line_layer_name, point_layer_name in line_layers.items():
    line_layer = QgsProject.instance().mapLayersByName(line_layer_name)
    if line_layer:
        create_point_layer_from_line_layer(line_layer[0], point_layer_name)
    else:
        print(f"Camada de linha '{line_layer_name}' não encontrada.")

# Verificar e plotar erros
check_and_plot_errors()

Regra 5:
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsWkbTypes, NULL
from PyQt5.QtCore import QVariant

def create_point_layer_from_line_layer(line_layer, output_layer_name):
    # Cria uma nova camada de ponto
    point_layer = QgsVectorLayer('Point?crs=' + line_layer.crs().authid(), output_layer_name, 'memory')
    point_layer_data = point_layer.dataProvider()

    # Copia todos os campos da camada de linha para a camada de ponto
    point_layer_data.addAttributes(line_layer.fields().toList())
    point_layer.updateFields()

    point_layer.startEditing()

    # Percorre todos os recursos na camada de linha
    for feature in line_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None:
            continue

        # Obtém os vértices da linha
        for vertex in geometry.vertices():
            point_feature = QgsFeature(point_layer.fields())
            point_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(vertex.x(), vertex.y())))
            point_feature.setAttributes(feature.attributes())
            point_layer.addFeature(point_feature)

    point_layer.commitChanges()

    # Adiciona a nova camada de ponto ao projeto QGIS
    QgsProject.instance().addMapLayer(point_layer)
    print(f"Camada de ponto '{output_layer_name}' criada a partir da camada de linha '{line_layer.name()}'.")

def validate_points():
    # Obter as camadas
    infra_elemento_viario_p = QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_elemento_viario_p")[0]
    infra_via_deslocamento_p = QgsProject.instance().mapLayersByName("infra_via_deslocamento_p")[0]

    # Filtrar pontos da camada infra_elemento_viario_p com tipo = 203
    infra_elemento_viario_p_203 = {feat.id(): feat for feat in infra_elemento_viario_p.getFeatures() if feat["tipo"] == 203}

    # Verificar pontos que satisfazem a regra 3
    common_ids = set(infra_elemento_viario_p_203.keys()) & {feat.id() for feat in infra_via_deslocamento_p.getFeatures()}

    # Verificar pontos que satisfazem a regra 4
    via_deslocamento_layer = QgsProject.instance().mapLayersByName("dados_projeto4_2024 — infra_via_deslocamento_l")[0]
    vertices_via_deslocamento = {QgsPointXY(vertex.x(), vertex.y()) for feature in via_deslocamento_layer.getFeatures() for vertex in feature.geometry().vertices()}

    valid_points = {feat_id for feat_id in common_ids if QgsPointXY(infra_elemento_viario_p_203[feat_id].geometry().asPoint()) in vertices_via_deslocamento}

    # Verificar atributos nr_pistas, nr_faixas e situacao_fisica
    error_layer = QgsVectorLayer("Point?crs=" + infra_via_deslocamento_p.crs().authid(), "Erro_Regra_5", "memory")
    error_provider = error_layer.dataProvider()

    error_provider.addAttributes([QgsField("ID", QVariant.Int), QgsField("Classificacao", QVariant.String)])
    error_layer.updateFields()

    error_layer.startEditing()

    for feat_id in valid_points:
        feat_elemento = infra_elemento_viario_p_203[feat_id]
        feat_deslocamento = infra_via_deslocamento_p.getFeature(feat_id)

        if (feat_elemento["nr_pistas"] != feat_deslocamento["nr_pistas"] or
                feat_elemento["nr_faixas"] != feat_deslocamento["nr_faixas"] or
                feat_elemento["situacao_fisica"] != feat_deslocamento["situacao_fisica"]):
            error_feature = QgsFeature(error_layer.fields())
            error_feature.setGeometry(feat_elemento.geometry())
            error_feature["ID"] = feat_id
            error_feature["Classificacao"] = "Erro na Regra 5"
            error_layer.addFeature(error_feature)

    error_layer.commitChanges()
    QgsProject.instance().addMapLayer(error_layer)
    print("Camada de erro 'Erro_Regra_5' criada com sucesso.")

# Transformar a camada de linha em uma camada de pontos
line_layer_name = "dados_projeto4_2024 — infra_via_deslocamento_l"
point_layer_name = "infra_via_deslocamento_p"

line_layer = QgsProject.instance().mapLayersByName(line_layer_name)
if line_layer:
    create_point_layer_from_line_layer(line_layer[0], point_layer_name)
else:
    print(f"Camada de linha '{line_layer_name}' não encontrada.")

# Validar os pontos e plotar erros
validate_points()

'''