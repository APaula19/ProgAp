from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox
from qgis.core import (QgsProcessingAlgorithm, QgsProcessingParameterFeatureSource, 
                       QgsProcessingParameterField, QgsProcessingParameterNumber, QgsProcessingParameterFeatureSink,
                       QgsFeatureSink, QgsFeature, QgsGeometry, QgsVectorLayer, QgsField, QgsProject)

class IdentificarMudancas(QgsProcessingAlgorithm):
    INPUT_LAYER_1 = 'INPUT_LAYER_1'
    INPUT_LAYER_2 = 'INPUT_LAYER_2'
    PONTOS_TRACKER = 'PONTOS_TRACKER'
    CHAVE_PRIMARIA = 'CHAVE_PRIMARIA'
    TOLERANCIA = 'TOLERANCIA'
    ATRIBUTOS_IGNORADOS = 'ATRIBUTOS_IGNORADOS'
    OUTPUT_LAYER = 'OUTPUT_LAYER'

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

    def processAlgorithm(self, parameters, context, feedback):
        camada_dia_1 = self.parameterAsSource(parameters, self.INPUT_LAYER_1, context)
        camada_dia_2 = self.parameterAsSource(parameters, self.INPUT_LAYER_2, context)
        camada_pontos = self.parameterAsSource(parameters, self.PONTOS_TRACKER, context)
        chave_primaria = self.parameterAsString(parameters, self.CHAVE_PRIMARIA, context)
        tolerancia = self.parameterAsDouble(parameters, self.TOLERANCIA, context)
        
        atributos_ignorados = self.get_ignored_attributes(camada_dia_1)

        atributos_comparar = [field.name() for field in camada_dia_1.fields() if field.name() not in atributos_ignorados]

        (sink, dest_id) = self.parameterAsSink(
            parameters,
            self.OUTPUT_LAYER,
            context,
            camada_dia_1.fields(),
            camada_dia_1.wkbType(),
            camada_dia_1.sourceCrs()
        )

        self.identificar_mudancas(camada_dia_1, camada_dia_2, sink, atributos_comparar, chave_primaria, tolerancia, context, feedback)

        return {self.OUTPUT_LAYER: dest_id}

    def get_ignored_attributes(self, layer):
        dialog = AtributosDialog([field.name() for field in layer.fields()])
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_selected_atributos()
        else:
            return []

    def identificar_mudancas(self, camada_dia_1, camada_dia_2, sink, atributos_comparar, chave_primaria, tolerancia, context, feedback):
        geom_type = camada_dia_1.wkbType()
        ids_dia_2 = {feature.attribute(chave_primaria): feature for feature in camada_dia_2.getFeatures()}

        for feature_dia_1 in camada_dia_1.getFeatures():
            if feedback.isCanceled():
                break
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
                    sink.addFeature(nova_feature, QgsFeatureSink.FastInsert)
            else:
                tipo_mudanca = "Removida"
                nova_feature = QgsFeature()
                nova_feature.setGeometry(geom_dia_1)
                nova_feature.setAttributes([id_dia_1, tipo_mudanca, ""])
                sink.addFeature(nova_feature, QgsFeatureSink.FastInsert)

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

def comparar_atributos(feature1, feature2, atributos_comparar):
    mudancas = []
    for nome_campo in atributos_comparar:
        valor1 = feature1[nome_campo]
        valor2 = feature2[nome_campo]
        if valor1 != valor2:
            mudancas.append(nome_campo)
    return mudancas

# Para registrar o algoritmo no QGIS
def classFactory(iface):
    from qgis.core import QgsApplication
    QgsApplication.processingRegistry().addProvider(IdentificarMudancas())
